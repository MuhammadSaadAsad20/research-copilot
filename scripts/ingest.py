"""
Index a PDF from the command line, without the web interface.

    python scripts\\ingest.py "C:\\path\\to\\paper.pdf"

Useful for checking the pipeline in isolation: it prints the page count, the
chunk count and the time taken, so a problem can be located to a stage.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Allow running this file directly, without installing the project.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.chunking import chunk_pages  # noqa: E402
from app.ingestion import IngestionError, document_id, read_pdf  # noqa: E402
from app.vectorstore import (  # noqa: E402
    VectorStoreError,
    add_chunks,
    document_exists,
    total_chunks,
)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__.strip())
        return 2

    path = Path(argv[0]).expanduser()
    if not path.is_file():
        print(f"No file at {path}")
        return 1

    problems = config.missing_config()
    if problems:
        for problem in problems:
            print(problem)
        return 1

    config.ensure_dirs()
    started = time.perf_counter()

    payload = path.read_bytes()
    if not payload.startswith(b"%PDF"):
        print(f"{path.name} is not a PDF.")
        return 1

    doc_id = document_id(payload)
    print(f"file    : {path.name}")
    print(f"doc_id  : {doc_id}")

    try:
        if document_exists(doc_id):
            print("status  : already indexed, nothing re-embedded")
            print(f"library : {total_chunks()} passages stored")
            return 0
    except VectorStoreError as exc:
        print(f"database: {exc}")
        return 1

    try:
        pages = read_pdf(path)
    except IngestionError as exc:
        print(f"error   : {exc}")
        return 1

    chunks = chunk_pages(pages, doc_id, path.name)
    if not chunks:
        print("error   : no passages long enough to index.")
        return 1

    average = sum(len(c.text) for c in chunks) / len(chunks)

    try:
        stored = add_chunks(chunks)
    except VectorStoreError as exc:
        print(f"error   : {exc}")
        return 1

    # Keep a copy alongside the vectors, matching what an upload would do.
    destination = config.UPLOAD_DIR / f"{doc_id}.pdf"
    if not destination.exists():
        destination.write_bytes(payload)

    elapsed = time.perf_counter() - started
    print(f"pages   : {len(pages)}")
    print(f"chunks  : {stored} (average {average:.0f} characters)")
    print(f"library : {total_chunks()} passages stored")
    print(f"time    : {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
