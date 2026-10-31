"""
Step 3 of the pipeline: turn chunks into vectors and store them.

An embedding is a list of numbers that represents the meaning of a piece of
text. Two texts about the same idea end up close together in that number space,
even when they share no words. Searching becomes a geometry problem: embed the
question, then find the chunks whose vectors sit nearest to it.

ChromaDB holds the vectors, the original text, and the metadata together, and
persists all of it to disk so the library survives a restart.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import chromadb
from openai import OpenAI

from app.chunking import Chunk
from app.config import (
    CHROMA_DIR,
    COLLECTION_NAME,
    EMBED_BATCH_SIZE,
    EMBEDDING_MODEL,
    OPENAI_API_KEY,
)


class VectorStoreError(Exception):
    """Raised when embedding or storage fails."""


@dataclass
class Retrieved:
    """A chunk that came back from a search, with its relevance score."""

    text: str
    doc_id: str
    filename: str
    page: int
    score: float  # 1.0 is a perfect match, 0.0 is unrelated


# --- Clients ---------------------------------------------------------------
# Both clients are cached so we build them once per process. They are created
# lazily rather than at import time, so the app can still start and show a
# helpful error when the API key is missing.


@lru_cache(maxsize=1)
def _openai() -> OpenAI:
    if not OPENAI_API_KEY:
        raise VectorStoreError(
            "OPENAI_API_KEY is not set. Add it to the .env file and restart."
        )
    return OpenAI(api_key=OPENAI_API_KEY)


@lru_cache(maxsize=1)
def _collection():
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        # Cosine distance compares the direction of two vectors rather than
        # their length, which is what we want for text similarity.
        metadata={"hnsw:space": "cosine"},
    )


# --- Embeddings ------------------------------------------------------------


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts, batching to stay within request limits."""
    if not texts:
        return []

    client = _openai()
    vectors: list[list[float]] = []

    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        try:
            response = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        except Exception as exc:
            raise VectorStoreError(f"Embedding request failed: {exc}") from exc

        # The API returns results in the same order as the input, but sorting
        # by index makes that guarantee explicit rather than assumed.
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors.extend(item.embedding for item in ordered)

    return vectors


# --- Writing ---------------------------------------------------------------


def add_chunks(chunks: list[Chunk]) -> int:
    """Embed chunks and write them to the database. Returns the count stored."""
    if not chunks:
        return 0

    vectors = embed_texts([chunk.text for chunk in chunks])

    _collection().upsert(
        ids=[chunk.chunk_id for chunk in chunks],
        embeddings=vectors,
        documents=[chunk.text for chunk in chunks],
        metadatas=[
            {
                "doc_id": chunk.doc_id,
                "filename": chunk.filename,
                "page": chunk.page,
                "index": chunk.index,
            }
            for chunk in chunks
        ],
    )
    return len(chunks)


def delete_document(doc_id: str) -> None:
    """Remove every chunk belonging to one document."""
    _collection().delete(where={"doc_id": doc_id})


# --- Reading ---------------------------------------------------------------


def search(question: str, top_k: int) -> list[Retrieved]:
    """Find the passages most relevant to a question."""
    if total_chunks() == 0:
        return []

    query_vector = embed_texts([question])[0]

    results = _collection().query(
        query_embeddings=[query_vector],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    # Chroma returns one list per query. We only sent one, so take index 0.
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    retrieved: list[Retrieved] = []
    for text, meta, distance in zip(documents, metadatas, distances):
        retrieved.append(
            Retrieved(
                text=text,
                doc_id=str(meta.get("doc_id", "")),
                filename=str(meta.get("filename", "Unknown document")),
                page=int(meta.get("page", 0)),
                # With cosine distance, 0 means identical. Flip it so a bigger
                # number means a better match, which reads more naturally.
                score=round(max(0.0, 1.0 - float(distance)), 3),
            )
        )
    return retrieved


def total_chunks() -> int:
    """How many passages are stored in total."""
    return _collection().count()


def list_documents() -> list[dict]:
    """
    Summarise the library: one entry per document, with page and chunk counts.

    Chroma has no native "group by", so we read the metadata and aggregate in
    Python. That is fine at the scale of a personal research library.
    """
    if total_chunks() == 0:
        return []

    records = _collection().get(include=["metadatas"])
    summary: dict[str, dict] = {}

    for meta in records["metadatas"]:
        doc_id = str(meta.get("doc_id", ""))
        entry = summary.setdefault(
            doc_id,
            {
                "doc_id": doc_id,
                "filename": str(meta.get("filename", "Unknown document")),
                "chunks": 0,
                "_pages": set(),
            },
        )
        entry["chunks"] += 1
        entry["_pages"].add(int(meta.get("page", 0)))

    documents = []
    for entry in summary.values():
        entry["pages"] = len(entry.pop("_pages"))
        documents.append(entry)

    return sorted(documents, key=lambda item: item["filename"].lower())


def document_exists(doc_id: str) -> bool:
    """True if any chunk from this document is already stored."""
    found = _collection().get(where={"doc_id": doc_id}, limit=1)
    return bool(found["ids"])
