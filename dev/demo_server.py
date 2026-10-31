"""Run the REAL app (real routes, real static files, real Chroma) with only
the two OpenAI calls stubbed, so the interface can be exercised end to end."""
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
from types import SimpleNamespace

DB = HERE / "chroma_demo"
if DB.exists():
    shutil.rmtree(DB)

from app import vectorstore as vs

vs.CHROMA_DIR = DB
DIM = 256


def fake_embed(texts):
    out = []
    for t in texts:
        v = [0.0] * DIM
        for w in t.lower().split():
            w = w.strip(".,:;()[]\"'")
            if not w:
                continue
            h = int(hashlib.sha256(w.encode()).hexdigest()[:8], 16)
            v[h % DIM] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


vs.embed_texts = fake_embed

from app import config, rag

# Keep uploads out of the real data/ folder too.
config.UPLOAD_DIR = HERE / "uploads_test"
config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

config.OPENAI_API_KEY = "sk-demo"
config.missing_config = lambda: []
rag.OPENAI_API_KEY = "sk-demo"

ANSWER = (
    "Lantern replaces recurrence with a gated retrieval mechanism [1], so the "
    "computation at each position no longer waits on the position before it "
    "[1][2]. Every position reaches every other in constant path length rather "
    "than a distance that grows with the sequence [2], which is what makes "
    "long-range dependencies learnable in practice [2][3]. The encoder stacks "
    "six identical layers, each pairing a multi-head retrieval block with a "
    "position-wise feed-forward network [3]."
)


class FakeCompletions:
    def create(self, **kw):
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=ANSWER))])


rag._openai = lambda: SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

# Seed the library, including a hostile filename.
from app.chunking import chunk_pages
from app.ingestion import document_id, read_pdf

PDFS = HERE / "pdfs"
# Pass --xss to also seed a hostile filename (for the escaping check).
# Off by default so a recorded demo looks clean.
seed = [
    ("lantern.pdf", "lantern.pdf"),
    ("beacon.pdf", "beacon.pdf"),
]
if "--xss" in sys.argv:
    seed.append(("lantern.pdf", "<script>alert('xss')</script>.pdf"))
for source, display in seed:
    path = PDFS / source
    payload = path.read_bytes()
    # Vary the bytes so the hostile-named copy is a distinct document.
    if display.startswith("<script>"):
        payload = payload + b"\n% variant\n"
        tmp = HERE / "variant.pdf"
        tmp.write_bytes(payload)
        path = tmp
    doc_id = document_id(payload)
    if not vs.document_exists(doc_id):
        vs.add_chunks(chunk_pages(read_pdf(path), doc_id, display))

from app.main import app  # noqa: E402

if __name__ == "__main__":
    import uvicorn

    ports = [a for a in sys.argv[1:] if a.isdigit()]
    port = int(ports[0]) if ports else 8011
    print(f"demo server on http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
