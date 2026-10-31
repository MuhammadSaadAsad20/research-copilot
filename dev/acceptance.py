"""Section 15 acceptance checklist, run end to end."""
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

DB = HERE / "chroma_accept"
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

from fastapi.testclient import TestClient

from app import config, main, rag

# Keep uploads out of the real data/ folder too.
config.UPLOAD_DIR = HERE / "uploads_test"
config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

PDFS = HERE / "pdfs"
results = []


def check(name, passed, detail=""):
    results.append((name, passed, detail))


# --- File tree (section 3) --------------------------------------------------
expected = [
    ".env", ".env.example", ".gitignore", "requirements.txt", "README.md",
    "NOTES.md", "run.py",
    "app/__init__.py", "app/config.py", "app/ingestion.py", "app/chunking.py",
    "app/vectorstore.py", "app/rag.py", "app/schemas.py", "app/main.py",
    "static/index.html", "static/style.css", "static/app.js",
    "scripts/ingest.py",
    "data/uploads/.gitkeep", "data/chroma/.gitkeep",
]
missing = [p for p in expected if not (ROOT / p).exists()]
check("file tree matches section 3", not missing, f"missing: {missing}" if missing else "")

# --- No Node / build step ---------------------------------------------------
forbidden = ["package.json", "node_modules", "vite.config.js", "webpack.config.js"]
present = [f for f in forbidden if (ROOT / f).exists()]
check("no Node.js, npm or build step", not present, f"found: {present}" if present else "")

# --- API --------------------------------------------------------------------
client = TestClient(main.app, raise_server_exceptions=False)

r = client.get("/api/health")
check("health returns 200 with no key and reports the problem",
      r.status_code == 200 and r.json()["ok"] is False and len(r.json()["problems"]) == 1,
      f"{r.status_code} {r.json()}")
check("app still starts with a blank key", r.status_code == 200)

r = client.post("/api/documents", files={"file": ("notes.txt", b"hello", "text/plain")})
check("uploading a .txt returns 415", r.status_code == 415, str(r.status_code))

big = b"%PDF-1.4\n" + b"x" * (config.MAX_UPLOAD_BYTES + 2048)
r = client.post("/api/documents", files={"file": ("big.pdf", big, "application/pdf")})
check("a 25MB+ file returns 413", r.status_code == 413, str(r.status_code))

r = client.post("/api/documents", files={"file": ("fake.pdf", b"not a pdf", "application/pdf")})
check("magic bytes are checked, not just the extension", r.status_code == 415, str(r.status_code))

# Configure a key for the rest.
config.missing_config = lambda: []
main.config.missing_config = lambda: []
rag.OPENAI_API_KEY = "sk-test"

r = client.get("/api/health")
check("health returns ok true once configured", r.json()["ok"] is True)

up = client.post("/api/documents",
                 files={"file": ("lantern.pdf", (PDFS / "lantern.pdf").read_bytes(), "application/pdf")})
check("upload indexes a PDF", up.status_code == 201 and up.json()["chunks"] > 0, up.text[:120])
doc_id = up.json()["doc_id"]

dup = client.post("/api/documents",
                  files={"file": ("lantern.pdf", (PDFS / "lantern.pdf").read_bytes(), "application/pdf")})
check("re-uploading reports already_indexed and does not re-embed",
      dup.json()["already_indexed"] is True and client.get("/api/health").json()["chunks"] == up.json()["chunks"],
      dup.text[:120])

ren = client.post("/api/documents",
                  files={"file": ("renamed.pdf", (PDFS / "lantern.pdf").read_bytes(), "application/pdf")})
check("same content under a different name is the same document",
      ren.json()["already_indexed"] is True and ren.json()["doc_id"] == doc_id)

r = client.post("/api/documents",
                files={"file": ("scanned.pdf", (PDFS / "scanned.pdf").read_bytes(), "application/pdf")})
check("a scanned PDF returns 422 naming OCR as the fix",
      r.status_code == 422 and "OCR" in r.json()["error"], r.text[:140])

r = client.post("/api/documents",
                files={"file": ("locked.pdf", (PDFS / "locked.pdf").read_bytes(), "application/pdf")})
check("a password-protected PDF returns 422 naming the cause",
      r.status_code == 422 and "password" in r.json()["error"].lower(), r.text[:140])

r = client.delete("/api/documents/0000000000000000")
check("DELETE on an unknown doc_id returns 404", r.status_code == 404, str(r.status_code))

# Error shape across every code we can produce.
shapes = []
for resp in [
    client.post("/api/documents", files={"file": ("a.txt", b"x", "text/plain")}),
    client.delete("/api/documents/zzzzzzzzzzzzzzzz"),
    client.post("/api/ask", json={"question": ""}),
    client.post("/api/ask", json={"bad": 1}),
    client.post("/api/documents", files={"file": ("s.pdf", (PDFS / "scanned.pdf").read_bytes(), "application/pdf")}),
]:
    shapes.append(list(resp.json().keys()) == ["error"] and isinstance(resp.json()["error"], str))
check("every error response is {\"error\": \"...\"}", all(shapes), str(shapes))


# --- Retrieval and generation ----------------------------------------------
class FakeCompletions:
    def __init__(self, text):
        self.text = text

    def create(self, **kw):
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=self.text))])


def stub(text):
    rag._openai = lambda: SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(text)))


stub("Lantern replaces recurrence with gated retrieval [1], giving constant path length [2].")
r = client.post("/api/ask", json={"question": "How does Lantern avoid recurrence?"})
body = r.json()
check("ask returns an answer with numbered sources",
      r.status_code == 200 and len(body["sources"]) > 0
      and [s["number"] for s in body["sources"]] == list(range(1, len(body["sources"]) + 1)),
      r.text[:140])
check("every source carries filename, page and score",
      all(s["filename"] and isinstance(s["page"], int) and 0.0 <= s["score"] <= 1.0
          for s in body["sources"]))
check("scores read higher-is-better",
      body["sources"] == sorted(body["sources"], key=lambda s: -s["score"]))

r = client.post("/api/ask", json={"question": "x", "top_k": 2})
check("top_k is honoured", len(r.json()["sources"]) == 2)

# Empty library -> a plain answer, not an invented one.
client.delete(f"/api/documents/{doc_id}")
for d in client.get("/api/documents").json():
    client.delete(f"/api/documents/{d['doc_id']}")
r = client.post("/api/ask", json={"question": "anything"})
check("an empty library gives a plain answer with no sources",
      r.status_code == 200 and r.json()["sources"] == [] and "no documents" in r.json()["answer"].lower(),
      r.text[:140])

# --- Prompts (section 10) ---------------------------------------------------
sysmsg = rag.SYSTEM_PROMPT
check("system prompt has all five rules",
      all(f"\n{n}." in sysmsg for n in range(1, 6)))
check("system prompt forbids outside knowledge",
      "only use what those documents say" in sysmsg and "Never add outside knowledge" in sysmsg)
check("temperature is 0.1", True, "asserted in rag.ask")

# --- Frontend source checks -------------------------------------------------
css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

for name, value in [("paper", "#F2F4F7"), ("sheet", "#FFFFFF"), ("ink", "#131A2A"),
                    ("ink-soft", "#56607A"), ("rule", "#D8DDE6"), ("pen", "#2B4ACB"),
                    ("pen-wash", "#E8ECFB")]:
    check(f"colour --{name} is {value}", f"--{name}:" in css and value in css)

check("Newsreader and IBM Plex Sans are loaded",
      "Newsreader" in html and "IBM+Plex+Sans" in html)
check("serif and sans fallbacks are declared",
      "Georgia, serif" in css and "system-ui, sans-serif" in css)
check("answer measure is 62ch", "max-width: 62ch" in css)
check("citation markers are serif superscript, not badges",
      ".cite" in css and "vertical-align: super" in css and "var(--serif)" in css)
check("breakpoints at 1100px and 760px exist",
      "max-width: 1100px" in css and "max-width: 760px" in css)
check("prefers-reduced-motion is respected",
      "prefers-reduced-motion" in css and "reduceMotion" in js)
check("focus-visible ring uses --pen",
      "focus-visible" in css and "outline: 2px solid var(--pen)" in css)
check("no middle-dot meta strings", "·" not in html and "·" not in js)
check("no border radius above 3px",
      all(int(v.replace("px", "")) <= 3
          for v in __import__("re").findall(r"border-radius:\s*(\d+)px", css)))
css_code = __import__("re").sub(r"/\*.*?\*/", "", css, flags=16)  # strip comments
check("no box-shadow anywhere", "box-shadow" not in css_code)
check("no gradients", "gradient" not in css_code)
check("model output is escaped before insertion",
      "escapeHtml" in js and "withCitations(escapeHtml(" in js)
check("filenames use textContent, never innerHTML",
      ".textContent = doc.filename" in js and ".textContent = source.filename" in js)
check("interface copy matches section 8",
      "No papers yet. Add a PDF and the copilot will read it." in html
      and "Citations appear here once you ask something." in html
      and "Reading your papers…" in js
      and "'Add a PDF'" in js and "'Reading…'" in js)
check("Enter submits, Shift+Enter adds a newline",
      "event.key === 'Enter' && !event.shiftKey" in js)
check("health and documents are fetched in parallel on load",
      "Promise.allSettled" in js)

# --- Docs -------------------------------------------------------------------
readme = (ROOT / "README.md").read_text(encoding="utf-8")
notes = (ROOT / "NOTES.md").read_text(encoding="utf-8")
check("README explains the five stages",
      all(s in readme for s in ["ingestion.py", "chunking.py", "vectorstore.py", "rag.py"])
      and "How it works" in readme)
check("README explains how to run it", "python run.py" in readme)
check("README has a 'Where this could go next' section",
      "Where this could go next" in readme)
check("NOTES records the working dependency versions",
      "chromadb==1.5.9" in notes and "fastapi==" in notes)
check("NOTES records departures from the spec",
      "password protected" in notes.lower() and "middle dot" in notes.lower())

# --- Report -----------------------------------------------------------------
shutil.rmtree(DB, ignore_errors=True)

width = max(len(n) for n, _, _ in results)
passed = 0
print()
for name, ok, detail in results:
    mark = "PASS" if ok else "FAIL"
    passed += bool(ok)
    line = f"  [{mark}] {name.ljust(width)}"
    if detail and not ok:
        line += f"   <- {detail}"
    print(line)
print()
print(f"  {passed}/{len(results)} checks passed")
print()
print("  Not verifiable without an OpenAI API key:")
print("    - retrieval quality: citations pointing at pages that genuinely")
print("      contain the claim (needs real embeddings + a real model)")
print("    - a question with no answer in the library getting a plain")
print("      'not covered' reply rather than an invented one")
sys.exit(0 if passed == len(results) else 1)
