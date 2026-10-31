"""
Central configuration for the Research Copilot.

Everything tunable lives here, and every value can be overridden from the .env
file at the project root. Nothing else in the codebase calls os.getenv, so this
file is the single place to look when you want to know how the app is set up.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# BASE_DIR is the project root (the folder containing app/, static/, data/).
# __file__ is app/config.py, so .parent is app/ and .parent.parent is the root.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load the .env file into the environment. This is a no-op if the file is
# missing, which is why every value below also has a sensible default.
load_dotenv(BASE_DIR / ".env")


# --- Credentials -----------------------------------------------------------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()


# --- Models ----------------------------------------------------------------

# The embedding model turns text into vectors. Small, fast, cheap, and good
# enough for retrieval over a personal document library.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# The chat model writes the final answer from the retrieved passages.
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")


# --- Chunking --------------------------------------------------------------

# Characters per chunk, and how much neighbouring chunks overlap. Overlap
# prevents a sentence that straddles a boundary from being lost to both sides.
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))

# Chunks shorter than this are dropped. They are usually page headers, figure
# labels, or stray line numbers, and they pollute retrieval results.
MIN_CHUNK_CHARS = int(os.getenv("MIN_CHUNK_CHARS", "60"))


# --- Retrieval -------------------------------------------------------------

# How many passages to pull back for each question.
TOP_K = int(os.getenv("TOP_K", "5"))

# How many texts to send to the embedding API in one request. Keeps us well
# under the per-request token ceiling while staying efficient.
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "64"))


# --- Limits ----------------------------------------------------------------

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


# --- Storage ---------------------------------------------------------------

DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"       # the original PDF files
CHROMA_DIR = DATA_DIR / "chroma"        # the persistent vector database
STATIC_DIR = BASE_DIR / "static"        # the web interface

COLLECTION_NAME = os.getenv("COLLECTION_NAME", "research_copilot")


def ensure_dirs() -> None:
    """Create the storage folders if they do not exist yet."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)


def missing_config() -> list[str]:
    """
    Return a list of human-readable problems with the current configuration.
    An empty list means the app is ready to run.
    """
    problems: list[str] = []
    if not OPENAI_API_KEY:
        problems.append(
            "OPENAI_API_KEY is not set. Add it to the .env file in the project root."
        )
    return problems
