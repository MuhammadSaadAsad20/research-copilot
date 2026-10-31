"""
Step 1 of the pipeline: turn a PDF file into clean, page-numbered text.

We deliberately keep the page number attached to every piece of text. That is
what makes an honest citation possible later on: when the copilot says a claim
came from page 7, it really did.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass
class Page:
    """One page of extracted text."""

    number: int  # 1-based, matching what a human sees in a PDF reader
    text: str


class IngestionError(Exception):
    """Raised when a PDF cannot be read or contains no extractable text."""


def document_id(pdf_bytes: bytes) -> str:
    """
    A stable id derived from the file's contents.

    Using the content hash rather than the filename means that uploading the
    same paper twice is recognised as the same document, even if it was renamed.
    """
    return hashlib.sha256(pdf_bytes).hexdigest()[:16]


def clean_text(raw: str) -> str:
    """
    Tidy the text that pypdf gives us.

    PDF extraction produces a lot of noise: words split across lines with
    hyphens, single newlines in the middle of sentences, and runs of blank
    space. Cleaning here means the chunker sees readable prose, which produces
    better chunks and therefore better retrieval.
    """
    # Join words that were hyphenated across a line break: "atten-\ntion".
    text = re.sub(r"-\n(?=\w)", "", raw)

    # A single newline inside a paragraph is a line wrap, not a break. Turn it
    # into a space. Two or more newlines are a real paragraph break, so keep one.
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)

    # Collapse runs of spaces and tabs.
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()


def read_pdf(path: Path) -> list[Page]:
    """
    Read a PDF from disk and return its pages as cleaned text.

    Pages with no extractable text are skipped. That normally means the page is
    a scanned image, which would need OCR to read.
    """
    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # pypdf raises a variety of exception types
        raise IngestionError(f"Could not open the PDF: {exc}") from exc

    if reader.is_encrypted:
        # Some PDFs are encrypted with an empty password and open fine.
        try:
            reader.decrypt("")
        except Exception as exc:
            raise IngestionError(
                "This PDF is password protected, so its text cannot be read."
            ) from exc

    pages: list[Page] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception:
            # One unreadable page should not sink the whole document.
            raw = ""

        text = clean_text(raw)
        if text:
            pages.append(Page(number=index, text=text))

    if not pages:
        raise IngestionError(
            "No text could be extracted. This PDF is probably a scan, which "
            "would need OCR before it can be searched."
        )

    return pages
