"""
Step 2 of the pipeline: split page text into chunks.

A whole page is too much to hand a language model as a single citation, and a
single sentence is too little to carry meaning on its own. Chunks sit in
between: big enough to be self-contained, small enough to be precise.

We split each page separately rather than splitting the document as one long
string. That costs a little context at page boundaries but guarantees every
chunk belongs to exactly one page, which keeps citations exact.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import CHUNK_OVERLAP, CHUNK_SIZE, MIN_CHUNK_CHARS
from app.ingestion import Page


@dataclass
class Chunk:
    """A retrievable passage, with enough metadata to cite it."""

    chunk_id: str       # unique across the whole database
    doc_id: str         # which document it came from
    filename: str       # the document's display name
    page: int           # the page it appeared on
    index: int          # its position within the document, for stable ordering
    text: str


def _splitter() -> RecursiveCharacterTextSplitter:
    """
    Build the splitter.

    RecursiveCharacterTextSplitter tries the separators in order, falling back
    to the next one only when a piece is still too big. So it breaks on
    paragraphs first, then sentences, then words, and only splits mid-word as a
    last resort. That is why chunks tend to end at natural boundaries.
    """
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )


def chunk_pages(pages: list[Page], doc_id: str, filename: str) -> list[Chunk]:
    """Turn a document's pages into a flat, ordered list of chunks."""
    splitter = _splitter()
    chunks: list[Chunk] = []
    position = 0

    for page in pages:
        for piece in splitter.split_text(page.text):
            piece = piece.strip()

            # Drop fragments too short to be useful. These are almost always
            # running headers, page numbers, or figure captions on their own.
            if len(piece) < MIN_CHUNK_CHARS:
                continue

            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}:{position}",
                    doc_id=doc_id,
                    filename=filename,
                    page=page.number,
                    index=position,
                    text=piece,
                )
            )
            position += 1

    return chunks
