"""Exercise the ChromaDB wiring without an OpenAI key.

Only the network call is replaced. Everything else - metadata typing, the
query result shape, the distance-to-score conversion, aggregation, deletion -
is the real code from app/vectorstore.py.
"""
import sys
from pathlib import Path

# Run from anywhere: put the project root on the import path.
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import hashlib
import math
import shutil
import sys
from pathlib import Path

TEST_DB = HERE / "chroma_test"
if TEST_DB.exists():
    shutil.rmtree(TEST_DB)

from app import vectorstore as vs

# Point the store at a throwaway database before the client is built.
vs.CHROMA_DIR = TEST_DB

DIM = 256


def fake_embed(texts):
    """Deterministic hashed bag-of-words. Similar text -> similar vector."""
    out = []
    for t in texts:
        v = [0.0] * DIM
        for word in t.lower().split():
            word = word.strip(".,:;()[]\"'")
            if not word:
                continue
            h = int(hashlib.sha256(word.encode()).hexdigest()[:8], 16)
            v[h % DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / norm for x in v])
    return out


vs.embed_texts = fake_embed

from app.chunking import chunk_pages
from app.ingestion import document_id, read_pdf

pdfs = HERE / "pdfs"

print("empty store")
print("  total_chunks()  :", vs.total_chunks())
print("  list_documents():", vs.list_documents())
print("  search()        :", vs.search("anything", 5))
print()

stored = {}
for name in ("lantern.pdf", "beacon.pdf"):
    path = pdfs / name
    doc_id = document_id(path.read_bytes())
    pages = read_pdf(path)
    chunks = chunk_pages(pages, doc_id, name)
    n = vs.add_chunks(chunks)
    stored[name] = (doc_id, len(pages), n)
    print(f"indexed {name}: doc_id={doc_id} pages={len(pages)} chunks={n}")

print()
print("total_chunks() :", vs.total_chunks())
print("list_documents():")
for d in vs.list_documents():
    print("  ", d)
print()

lantern_id = stored["lantern.pdf"][0]
print("document_exists(lantern)     :", vs.document_exists(lantern_id))
print("document_exists(bogus)       :", vs.document_exists("0000000000000000"))
print()

print("search('how does it avoid recurrence?', top_k=5)")
for r in vs.search("how does the model avoid recurrence", 5):
    print(f"   score={r.score:<6} page={r.page:<3} {r.filename:<12} {r.text[:72]}...")
print()

hits = vs.search("masked token pretraining objective", 3)
print("search('masked token pretraining objective', top_k=3)")
for r in hits:
    print(f"   score={r.score:<6} page={r.page:<3} {r.filename:<12} {r.text[:72]}...")
print()

print("--- pitfall checks ---")
print("  scores are floats in 0..1        :",
      all(isinstance(r.score, float) and 0.0 <= r.score <= 1.0 for r in hits))
print("  higher score = better match      :",
      hits[0].score >= hits[-1].score)
print("  page is int                      :", all(isinstance(r.page, int) for r in hits))
print("  top hit for a Beacon question is Beacon:", hits[0].filename == "beacon.pdf")
print("  top_k respected                  :", len(hits) == 3)
print()

# Re-adding the same chunks must not duplicate (upsert by chunk_id).
before = vs.total_chunks()
path = pdfs / "lantern.pdf"
vs.add_chunks(chunk_pages(read_pdf(path), lantern_id, "lantern.pdf"))
print("re-upsert same doc: before =", before, "after =", vs.total_chunks(),
      "-> no duplicates:", before == vs.total_chunks())

vs.delete_document(lantern_id)
print("after delete_document(lantern): total =", vs.total_chunks(),
      "| documents =", [d["filename"] for d in vs.list_documents()])
print("document_exists(lantern) now  :", vs.document_exists(lantern_id))

shutil.rmtree(TEST_DB, ignore_errors=True)
print()
print("vectorstore wiring OK")
