"""Run scripts/ingest.py end to end with only the embedding call stubbed."""
import sys
from pathlib import Path

# Run from anywhere: put the project root on the import path.
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import hashlib
import importlib.util
import math
import shutil
import sys
from pathlib import Path

DB = HERE / "chroma_cli"
if DB.exists():
    shutil.rmtree(DB)

from app import config, vectorstore as vs

# Keep uploads out of the real data/ folder too.
config.UPLOAD_DIR = HERE / "uploads_test"
config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

vs.CHROMA_DIR = DB
config.missing_config = lambda: []
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

spec = importlib.util.spec_from_file_location("ingest_cli", ROOT / "scripts" / "ingest.py")
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)
ingest.config.missing_config = lambda: []

PDFS = HERE / "pdfs"

print("=== first run ===")
code = ingest.main([str(PDFS / "lantern.pdf")])
print("exit code:", code)
print()

print("=== second run on the same file (must not re-embed) ===")
code2 = ingest.main([str(PDFS / "lantern.pdf")])
print("exit code:", code2)
print()

print("=== a scan ===")
code3 = ingest.main([str(PDFS / "scanned.pdf")])
print("exit code:", code3)
print()

print("=== password protected ===")
code4 = ingest.main([str(PDFS / "locked.pdf")])
print("exit code:", code4)
print()

print("=== no arguments ===")
code5 = ingest.main([])
print("exit code:", code5)
print()

print("=== missing file ===")
code6 = ingest.main([str(PDFS / "nope.pdf")])
print("exit code:", code6)
print()

print("summary:",
      {"first": code, "duplicate": code2, "scan": code3,
       "locked": code4, "no args": code5, "missing": code6})

shutil.rmtree(DB, ignore_errors=True)
