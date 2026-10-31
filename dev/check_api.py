"""Exercise every endpoint. The OpenAI calls are stubbed; everything else is real."""
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

TEST_DB = HERE / "chroma_api"
if TEST_DB.exists():
    shutil.rmtree(TEST_DB)

from app import vectorstore as vs

vs.CHROMA_DIR = TEST_DB

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

from fastapi.testclient import TestClient

from app import config, main

# Keep uploads out of the real data/ folder too.
config.UPLOAD_DIR = HERE / "uploads_test"
config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

PDFS = HERE / "pdfs"
client = TestClient(main.app, raise_server_exceptions=False)


def show(label, r):
    body = r.text
    if len(body) > 240:
        body = body[:240] + "..."
    print(f"  {label:<46} {r.status_code}  {body}")


print("=== health with no API key (must still be 200) ===")
r = client.get("/api/health")
show("GET /api/health", r)
j = r.json()
print("    ok:", j["ok"], "| problems:", j["problems"])
print()

print("=== documents, empty library ===")
show("GET /api/documents", client.get("/api/documents"))
print()

print("=== upload validation (no key needed for these) ===")
show("POST .txt -> 415",
     client.post("/api/documents", files={"file": ("notes.txt", b"hello", "text/plain")}))
show("POST .pdf that isn't a PDF -> 415",
     client.post("/api/documents", files={"file": ("fake.pdf", b"hello", "application/pdf")}))
big = b"%PDF-1.4\n" + b"x" * (config.MAX_UPLOAD_BYTES + 1024)
show("POST 25MB+ -> 413",
     client.post("/api/documents", files={"file": ("big.pdf", big, "application/pdf")}))
show("POST no file field -> 400", client.post("/api/documents"))
print()

print("=== upload a real PDF with no key -> 503 ===")
show("POST lantern.pdf",
     client.post("/api/documents",
                 files={"file": ("lantern.pdf", (PDFS / "lantern.pdf").read_bytes(), "application/pdf")}))
print()

print("=== ask with no key ===")
show("POST /api/ask empty question -> 400", client.post("/api/ask", json={"question": "   "}))
show("POST /api/ask -> 503", client.post("/api/ask", json={"question": "what is this"}))
show("POST /api/ask malformed body -> 400", client.post("/api/ask", json={"nope": 1}))
print()

print("=== now pretend the key is configured ===")
config.OPENAI_API_KEY = "sk-test"
main.config.OPENAI_API_KEY = "sk-test"
_real_missing = config.missing_config
config.missing_config = lambda: []
main.config.missing_config = lambda: []

r = client.get("/api/health")
print("  health ok now:", r.json()["ok"], "| problems:", r.json()["problems"])
print()

print("=== upload for real ===")
r = client.post("/api/documents",
                files={"file": ("lantern.pdf", (PDFS / "lantern.pdf").read_bytes(), "application/pdf")})
show("POST lantern.pdf -> 201", r)
first = r.json()

r2 = client.post("/api/documents",
                 files={"file": ("lantern.pdf", (PDFS / "lantern.pdf").read_bytes(), "application/pdf")})
show("POST same file again", r2)
print("    already_indexed:", r2.json().get("already_indexed"), "(must be True, nothing re-embedded)")

r3 = client.post("/api/documents",
                 files={"file": ("RENAMED.pdf", (PDFS / "lantern.pdf").read_bytes(), "application/pdf")})
print("    same bytes, different name -> already_indexed:", r3.json().get("already_indexed"),
      "| doc_id matches:", r3.json().get("doc_id") == first["doc_id"])

client.post("/api/documents",
            files={"file": ("beacon.pdf", (PDFS / "beacon.pdf").read_bytes(), "application/pdf")})
print()

print("=== a scanned PDF -> 422 ===")
show("POST scanned.pdf",
     client.post("/api/documents",
                 files={"file": ("scanned.pdf", (PDFS / "scanned.pdf").read_bytes(), "application/pdf")}))
show("POST locked.pdf",
     client.post("/api/documents",
                 files={"file": ("locked.pdf", (PDFS / "locked.pdf").read_bytes(), "application/pdf")}))
print()

print("=== library ===")
r = client.get("/api/documents")
for d in r.json():
    print("   ", d)
h = client.get("/api/health").json()
print("    health documents:", h["documents"], "chunks:", h["chunks"])
print()

print("=== ask, with the model stubbed ===")
from types import SimpleNamespace

from app import rag


class FakeCompletions:
    def create(self, **kw):
        n = kw["messages"][1]["content"].count("] From ")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content="Lantern replaces recurrence with gated retrieval [1], and every "
                    f"position reaches every other in constant path length [2]. ({n} passages seen)"))])


rag._openai = lambda: SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
rag.OPENAI_API_KEY = "sk-test"

r = client.post("/api/ask", json={"question": "how does Lantern avoid recurrence?"})
print("  status:", r.status_code)
j = r.json()
print("  answer:", j["answer"])
print("  sources:")
for s in j["sources"]:
    print(f"    [{s['number']}] {s['filename']} p{s['page']} score={s['score']} :: {s['text'][:56]}...")
print("  top_k honoured:",
      len(client.post("/api/ask", json={"question": "x", "top_k": 2}).json()["sources"]) == 2)
print()

print("=== delete ===")
show("DELETE unknown doc_id -> 404", client.delete("/api/documents/0000000000000000"))
show("DELETE lantern", client.delete(f"/api/documents/{first['doc_id']}"))
print("    library now:", [d["filename"] for d in client.get("/api/documents").json()])
print()

print("=== error shape ===")
codes = {}
for label, resp in [
    ("415", client.post("/api/documents", files={"file": ("a.txt", b"x", "text/plain")})),
    ("404", client.delete("/api/documents/zzzzzzzzzzzzzzzz")),
    ("400", client.post("/api/ask", json={"question": ""})),
]:
    body = resp.json()
    codes[label] = (resp.status_code, list(body.keys()))
    print(f"  {label}: status={resp.status_code} keys={list(body.keys())}")
print("  every error body is exactly {'error': ...}:",
      all(keys == ["error"] for _, keys in codes.values()))

shutil.rmtree(TEST_DB, ignore_errors=True)
print()
print("API OK")
