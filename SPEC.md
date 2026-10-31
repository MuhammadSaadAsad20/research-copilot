# Intelligent Research Copilot — Build Specification

A complete build brief. Follow it as written. Where it pins down a decision, take the decision as given rather than substituting a preference. Where it is silent, use judgement and note the choice in `NOTES.md`.

---

## 1. What this is

A local web application. The user drops in research PDFs, asks questions in plain English, and gets an answer written only from those PDFs — with every claim carrying a numbered citation that resolves to a real page in a real document.

The point of difference is trust. Most retrieval demos bury their sources in a collapsed panel at the bottom. Here the citations are permanent furniture: they sit in a margin beside the answer, numbered, always visible, and clicking a citation marker in the prose jumps to the passage it came from.

**Definition of done:** a person can run one command, open a browser, upload a PDF, ask a question, and read an answer whose citations they can verify against the source pages — without touching a terminal again.

---

## 2. Environment and constraints

| Item | Value |
|---|---|
| OS | Windows 11 |
| Python | 3.14, in a virtual environment at the project root |
| Project root | `C:\Users\saada\OneDrive\Desktop\research-copilot` |
| Backend | FastAPI + Uvicorn |
| Frontend | Static HTML/CSS/JS served by FastAPI |
| Embeddings | OpenAI `text-embedding-3-small` |
| Generation | OpenAI `gpt-4o-mini` (configurable) |
| Vector store | ChromaDB, persistent, local |
| Secrets | `.env` at project root, already contains `OPENAI_API_KEY` |

**Hard constraint: no Node.js, no npm, no build step.** The frontend is hand-written HTML, CSS, and vanilla JavaScript served directly by FastAPI. Adding a second toolchain is the most likely way for this project to stop working on the target machine. Do not introduce React, Vite, Tailwind, or a bundler.

Some project files already exist (`requirements.txt`, `.env`, `test_setup.py`, `NOTES.md`). Read before overwriting. Preserve `NOTES.md` — append to it, never replace it.

---

## 3. File tree

Build exactly this structure.

```
research-copilot/
├── .env                     # exists — do not overwrite, only read
├── .env.example             # create: same keys, no values
├── .gitignore               # create or extend
├── requirements.txt         # rewrite to match section 11
├── README.md                # create
├── NOTES.md                 # exists — append only
├── run.py                   # convenience launcher
├── app/
│   ├── __init__.py
│   ├── config.py            # all settings, single source of truth
│   ├── ingestion.py         # PDF  -> pages of clean text
│   ├── chunking.py          # pages -> chunks
│   ├── vectorstore.py       # chunks -> embeddings -> ChromaDB, and search
│   ├── rag.py               # retrieve + generate a cited answer
│   ├── schemas.py           # Pydantic request/response models
│   └── main.py              # FastAPI app, routes, error handling
├── static/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── scripts/
│   └── ingest.py            # index a PDF from the command line
└── data/
    ├── uploads/.gitkeep     # original PDFs
    └── chroma/.gitkeep      # the vector database
```

`reference/` (shipped alongside this spec) contains working implementations of `config.py`, `ingestion.py`, `chunking.py`, `vectorstore.py`, and `rag.py`. **Use those five files as the starting point** — copy them into `app/`, verify them against this spec, and fix anything that has drifted. Build `schemas.py`, `main.py`, the frontend, the scripts, and the docs fresh.

---

## 4. Pipeline

Five stages. Each one is a module, and each one can be tested on its own.

```
PDF file
  │
  ├─ 1. ingestion.py   pypdf reads each page. Text is cleaned: de-hyphenate
  │                    across line breaks, collapse wrapped lines into
  │                    paragraphs, squeeze whitespace. Page numbers are kept.
  │
  ├─ 2. chunking.py    Each page is split independently into ~800-char chunks
  │                    with 150 chars of overlap. Splitting per page (rather
  │                    than over the whole document) costs a little context at
  │                    page boundaries and buys exact citations. That trade is
  │                    deliberate — do not "improve" it by splitting globally.
  │
  ├─ 3. vectorstore.py Chunks are embedded in batches of 64 and upserted into
  │                    ChromaDB with cosine distance, alongside their text and
  │                    metadata.
  │
  ├─ 4. vectorstore.py A question is embedded and the nearest 5 chunks are
  │       (search)     returned, with cosine distance converted to a 0–1 score
  │                    where higher is better.
  │
  └─ 5. rag.py         Those chunks are numbered and given to the chat model as
                       the only permitted source. It writes an answer citing
                       [1], [2]. Passage N in the prompt is source N in the
                       response — that alignment is what makes the margin work.
```

---

## 5. Data model

Plain dataclasses in the pipeline modules. Pydantic models only at the HTTP boundary.

```python
# ingestion.py
@dataclass
class Page:
    number: int          # 1-based, matches what a human sees in a PDF reader
    text: str

# chunking.py
@dataclass
class Chunk:
    chunk_id: str        # f"{doc_id}:{index}" — unique across the database
    doc_id: str          # sha256 of file bytes, first 16 hex chars
    filename: str        # display name
    page: int
    index: int           # position within the document
    text: str

# vectorstore.py
@dataclass
class Retrieved:
    text: str
    doc_id: str
    filename: str
    page: int
    score: float         # 0.0–1.0, higher is better

# rag.py
@dataclass
class Source:
    number: int          # 1-based citation number
    filename: str
    page: int
    score: float
    text: str

@dataclass
class Answer:
    question: str
    answer: str
    sources: list[Source]
```

`doc_id` is derived from file **content**, not filename. Uploading the same paper twice under a different name must be recognised as the same document.

---

## 6. Module contracts

Exact signatures. Do not rename or change shapes.

### `app/config.py`
Every tunable value, read from `.env` with defaults. No other module calls `os.getenv`.

```python
BASE_DIR, DATA_DIR, UPLOAD_DIR, CHROMA_DIR, STATIC_DIR   # Path objects
OPENAI_API_KEY: str
EMBEDDING_MODEL: str = "text-embedding-3-small"
CHAT_MODEL: str = "gpt-4o-mini"
CHUNK_SIZE: int = 800
CHUNK_OVERLAP: int = 150
MIN_CHUNK_CHARS: int = 60
TOP_K: int = 5
EMBED_BATCH_SIZE: int = 64
MAX_UPLOAD_MB: int = 25
COLLECTION_NAME: str = "research_copilot"

def ensure_dirs() -> None
def missing_config() -> list[str]     # empty list means ready to run
```

### `app/ingestion.py`
```python
class IngestionError(Exception)
def document_id(pdf_bytes: bytes) -> str
def clean_text(raw: str) -> str
def read_pdf(path: Path) -> list[Page]
```
Raise `IngestionError` when the file will not open, is password protected, or yields no extractable text (a scan). The scan message must say OCR is the fix. A single unreadable page must not fail the whole document.

### `app/chunking.py`
```python
def chunk_pages(pages: list[Page], doc_id: str, filename: str) -> list[Chunk]
```
Uses `RecursiveCharacterTextSplitter` with separators `["\n\n", "\n", ". ", " ", ""]`. Drops chunks shorter than `MIN_CHUNK_CHARS` — those are running headers and figure labels, and they poison retrieval.

### `app/vectorstore.py`
```python
class VectorStoreError(Exception)
def embed_texts(texts: list[str]) -> list[list[float]]
def add_chunks(chunks: list[Chunk]) -> int
def delete_document(doc_id: str) -> None
def search(question: str, top_k: int) -> list[Retrieved]
def total_chunks() -> int
def list_documents() -> list[dict]    # {doc_id, filename, pages, chunks}
def document_exists(doc_id: str) -> bool
```
The OpenAI and Chroma clients are built lazily and cached with `@lru_cache(maxsize=1)`, so the app still starts and reports a useful error when the key is missing.

### `app/rag.py`
```python
class GenerationError(Exception)
def ask(question: str, top_k: int | None = None) -> Answer
```
Returns a friendly `Answer` with empty sources when the library is empty or nothing matched. Raises `GenerationError` when the key is missing or the model call fails.

---

## 7. HTTP API

All API routes are prefixed `/api`. All responses are JSON except the root.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Serve `static/index.html` |
| `GET` | `/api/health` | Readiness and library stats |
| `GET` | `/api/documents` | List indexed documents |
| `POST` | `/api/documents` | Upload and index a PDF |
| `DELETE` | `/api/documents/{doc_id}` | Remove a document and its vectors |
| `POST` | `/api/ask` | Ask a question |

**`GET /api/health` → 200**
```json
{
  "ok": true,
  "chat_model": "gpt-4o-mini",
  "embedding_model": "text-embedding-3-small",
  "documents": 3,
  "chunks": 214,
  "problems": []
}
```
`ok` is `false` and `problems` is non-empty when configuration is incomplete. This endpoint never returns an error status — it is the diagnostic.

**`POST /api/documents`** — `multipart/form-data`, field name `file`.
```json
{ "doc_id": "a1b2c3d4e5f60718", "filename": "attention.pdf",
  "pages": 15, "chunks": 66, "already_indexed": false }
```
When `document_exists(doc_id)` is already true, skip re-embedding, return the existing counts, and set `already_indexed: true`. Re-embedding a duplicate wastes money and is the kind of detail that separates a working demo from a real tool.

**`POST /api/ask`** — body `{ "question": str, "top_k": int | null }`
```json
{
  "question": "How does the transformer avoid recurrence?",
  "answer": "It replaces recurrence with self-attention [1], which lets every position attend to every other in constant path length [2].",
  "sources": [
    { "number": 1, "filename": "attention.pdf", "page": 3,
      "score": 0.612, "text": "The Transformer relies entirely on..." }
  ]
}
```

**Errors.** Every failure returns `{"error": "<plain sentence>"}` with a real status code. Register an exception handler so `HTTPException` and unhandled exceptions both produce that shape — the frontend should never have to parse two formats.

| Status | When |
|---|---|
| 400 | Empty question, malformed body |
| 404 | `doc_id` not in the library |
| 413 | Upload over `MAX_UPLOAD_MB` |
| 415 | Not a PDF (check extension **and** the `%PDF` magic bytes) |
| 422 | PDF unreadable or is a scan (`IngestionError`) |
| 502 | OpenAI call failed (`VectorStoreError`, `GenerationError`) |
| 503 | `missing_config()` is non-empty |

Error messages are written to the person reading them: say what happened and what to do. No stack traces, no apologies.

---

## 8. Design system

The subject is scholarship — reading dense papers and checking claims against sources. The visual language comes from that world: printed pages, marginalia, footnotes, blue pen annotation. Not from the generic AI-chat-app kit.

### Colour

Cool laser-printed paper, navy-shifted ink, ballpoint blue for anything that marks or references. Six values, no gradients.

```css
--paper:     #F2F4F7;   /* page ground — cool grey-blue, not cream */
--sheet:     #FFFFFF;   /* the document surface itself */
--ink:       #131A2A;   /* primary text — deliberately navy-shifted */
--ink-soft:  #56607A;   /* secondary text, metadata */
--rule:      #D8DDE6;   /* dividers and borders */
--pen:       #2B4ACB;   /* ballpoint blue — citations, links, focus */
--pen-wash:  #E8ECFB;   /* tint behind an active citation */
```

### Type

Two families, clearly distinct. The answer is a piece of writing to be read; everything around it is machinery.

- **Newsreader** (serif) — the answer text, document titles, citation numerals.
- **IBM Plex Sans** — interface chrome: buttons, labels, counts, filenames.

Load from Google Fonts with system fallbacks (`Georgia, serif` / `system-ui, sans-serif`).

```
13px  metadata, scores, page numbers        Plex Sans 400
14px  buttons, library entries, labels      Plex Sans 500
16px  input field, margin note text         Plex Sans 400 / Newsreader 400
18px  answer body                           Newsreader 400, line-height 1.65
21px  document titles in the library        Newsreader 400
28px  the one page title                    Newsreader 400
```

Answer column measure: `max-width: 62ch`. Never exceed 80 characters per line anywhere.

### Layout

Three columns. Left-aligned throughout — centred text would be wrong for a research tool.

```
┌────────────────────────────────────────────────────────────────────────┐
│  Research copilot                          3 papers · 214 passages      │  56px header
├──────────────┬─────────────────────────────────────┬───────────────────┤
│              │                                     │                   │
│  LIBRARY     │   ┌─────────────────────────────┐   │   MARGIN          │
│  240px       │   │ Ask about your papers…       │   │   300px           │
│              │   └─────────────────────────────┘   │                   │
│  Add a PDF   │                     [ Ask ]         │   ¹ attention.pdf  │
│              │                                     │     page 3 · 0.61 │
│  attention   │   ─────────────────────────────     │     "The Trans-   │
│  15 pp       │                                     │      former relies │
│  66 passages │   It replaces recurrence with       │      entirely…"    │
│              │   self-attention¹, which lets       │                   │
│  bert.pdf    │   every position attend to every    │   ² attention.pdf  │
│  9 pp        │   other in constant path length².   │     page 5 · 0.58 │
│  48 passages │                                     │     "Multi-head…"  │
│              │   ← max 62ch measure →              │                   │
└──────────────┴─────────────────────────────────────┴───────────────────┘
```

Below 1100px the margin moves under the answer. Below 760px the library collapses to a horizontal strip above the input.

### The one bold move

Citation markers are **true superscript numerals in the serif face**, exactly as a footnote appears in a printed paper — not pill badges, not coloured chips.

Behaviour:
- The frontend rewrites `[n]` in the answer text into `<sup><a>` markers.
- Clicking a marker gives the matching margin note a `--pen-wash` background and scrolls it into view.
- Hovering a margin note highlights every marker in the prose that points at it.
- Both directions are keyboard reachable with a visible `--pen` focus ring.

That is the memorable element. Everything else stays quiet: 3px border radius at most, one accent colour, no card shadows, no decorative gradients.

### Do not

These are the tells of a generated interface. Avoid all of them:

- Chat bubbles, or an answer that looks like a messaging thread.
- Sources hidden in a collapsible accordion at the bottom.
- Cream `#F4F1EA` grounds with terracotta accents; dark grounds with acid-green accents.
- Identical rounded cards with the same soft grey shadow under each.
- ALL-CAPS tracked-out eyebrow labels above headings.
- `→` appended to button text; meta strings joined with middle dots.
- Monospace for every small label.
- Fade-and-slide-up entrance animations on each section, or hover transitions on every element. Motion answers a user action or does not appear.

### Interface copy

Sentence case. Active voice. The button says what happens.

- Empty library: **"No papers yet. Add a PDF and the copilot will read it."**
- Empty margin: **"Citations appear here once you ask something."**
- Thinking: **"Reading your papers…"**
- Upload button: **"Add a PDF"** → while working, **"Reading…"**
- Ask button: **"Ask"**
- Delete confirm: **"Remove *filename* from the library?"**

---

## 9. Frontend behaviour

Single page. No router, no framework, no build.

**On load** — call `/api/health` and `/api/documents` in parallel. If `problems` is non-empty, show a single quiet banner under the header with the problem text and disable the ask input. Otherwise render the library.

**Upload** — `<input type="file" accept="application/pdf">` behind a styled label. On change, POST as `FormData`. Disable the control and swap the label to "Reading…" while in flight. On success, prepend the new document to the library and refresh the header counts. On `already_indexed: true`, say so in the library entry rather than adding a duplicate row.

**Ask** — Enter submits, Shift+Enter adds a newline. While waiting, disable the button and show "Reading your papers…" in the answer column. On success, render the answer with live citation markers and fill the margin. On error, replace the answer area with the message from `{"error": ...}` — styled as text, not as a red alert box.

**Delete** — an unobtrusive control on each library row. Confirm, then `DELETE`, then remove the row and refresh counts.

**Quality floor** — responsive to 360px; visible keyboard focus on every interactive element; `prefers-reduced-motion` respected; all text meets WCAG AA contrast; the file input remains reachable by keyboard.

**Security** — the answer text goes through a `[n]`-to-markup transform. Escape all other HTML before inserting. Never use `innerHTML` on raw model output or on filenames.

---

## 10. Prompts

Use these verbatim. They are load-bearing: rule 2 is what makes the margin possible, and rule 3 is what stops the model inventing an answer when the library does not contain one.

**System:**
```
You are a research assistant. You answer questions about a specific set of
documents, and you only use what those documents say.

Rules you always follow:
1. Use only the numbered passages provided. Never add outside knowledge, even
if you are confident it is correct.
2. Cite the passage number in square brackets after every claim, like [1] or
[2][4]. Every factual sentence needs at least one citation.
3. If the passages do not answer the question, say so plainly in one sentence
and stop. Do not speculate or pad.
4. Be direct and specific. Lead with the answer rather than restating the
question. Quote from the passages only when the exact wording matters.
5. Write in plain prose. Use a short list only when the answer really is a set
of parallel items.
```

**User message:**
```
[1] From "<filename>", page <n>:
<chunk text>

[2] From "<filename>", page <n>:
<chunk text>

---
Question: <the question>

Answer using only the passages above, citing each claim by number.
```

`temperature=0.1`. Low temperature keeps the model close to the source instead of paraphrasing creatively.

---

## 11. Dependencies

`requirements.txt`:

```
fastapi
uvicorn[standard]
python-multipart
python-dotenv
pypdf
langchain-text-splitters
openai
chromadb
```

`python-multipart` is not optional — FastAPI raises at import time on any route using `UploadFile` without it, and the error message does not say so clearly. Pin versions after the first successful install by running `pip freeze` and recording the working set in `NOTES.md`.

---

## 12. Setup and run

Windows, from the project root, with the virtual environment active:

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

`run.py` calls `config.ensure_dirs()` then serves `app.main:app` on `127.0.0.1:8000` with `reload=False`. Print the URL on startup so the user has something to click.

`scripts/ingest.py` takes a path and indexes a PDF without the web interface:
```powershell
python scripts\ingest.py "C:\path\to\paper.pdf"
```
It should print page count, chunk count, and time taken — useful for checking the pipeline in isolation when something goes wrong.

---

## 13. Known pitfalls

Address these directly rather than discovering them at runtime.

1. **Python 3.14 wheels.** `chromadb` has compiled dependencies and may not have a 3.14 wheel yet. If `pip install` fails to build, report it clearly and stop — do not silently swap in a different vector store. The fix is either a newer chromadb release or a 3.12 environment, and that is the user's decision to make.
2. **Chroma metadata types.** Values must be `str`, `int`, `float`, or `bool`. A `Path`, `None`, or a list will raise. Cast `page` and `index` to `int` explicitly.
3. **Chroma query result shape.** `collection.query()` returns one list *per query*. Since a single query vector is sent, read `results["documents"][0]`, not `results["documents"]`. Getting this wrong produces a confusing zip of nested lists.
4. **Distance, not similarity.** With `hnsw:space: cosine`, Chroma returns *distance* where 0 is a perfect match. Convert with `max(0.0, 1.0 - distance)` before showing a score, or the numbers will read backwards.
5. **`datetime.utcnow()` is deprecated.** Use `datetime.now(timezone.utc)` if timestamps are needed.
6. **Embedding order.** The API returns results in input order, but sort `response.data` by `.index` anyway so the guarantee is explicit rather than assumed.
7. **Large PDFs.** A 200-page paper produces hundreds of chunks and several embedding batches. Upload will take tens of seconds. The frontend must show progress state, not appear frozen.

---

## 14. Out of scope

Do not build these. They add failure surface without serving the definition of done.

- Streaming responses (the loading state is sufficient)
- User accounts, authentication, multi-user support
- Conversation history or follow-up questions with memory
- OCR for scanned PDFs
- Reranking, hybrid search, or query rewriting
- Docker, cloud deployment, CI
- A React rewrite of the frontend

If any of these are wanted later, note them in `README.md` under a short "Where this could go next" heading and leave it there.

---

## 15. Acceptance checklist

Verify each item before declaring the build finished.

**Pipeline**
- [ ] `python scripts\ingest.py <a real PDF>` prints page and chunk counts and exits 0
- [ ] Re-running it on the same file reports the document as already indexed and does not re-embed
- [ ] A password-protected or scanned PDF produces a clear message naming the cause

**API**
- [ ] `GET /api/health` returns `ok: true` and correct counts
- [ ] Temporarily blanking `OPENAI_API_KEY` makes `/api/health` return `ok: false` with a readable problem, and the app still starts
- [ ] Uploading a `.txt` returns 415; a 30 MB file returns 413
- [ ] `DELETE` on an unknown `doc_id` returns 404
- [ ] Every error response is shaped `{"error": "..."}`

**Retrieval quality**
- [ ] A question answerable from the PDF returns an answer whose citations point at pages that genuinely contain the claim
- [ ] A question with no answer in the library gets a plain "not covered" response, not an invented one

**Interface**
- [ ] Citation markers render as serif superscript numerals, not badges
- [ ] Clicking a marker highlights and scrolls to its margin note
- [ ] Hovering a margin note highlights its markers in the prose
- [ ] Layout holds at 1440px, 1100px, 760px, and 360px
- [ ] Every interactive element is keyboard reachable with a visible focus ring
- [ ] A filename containing `<script>` renders as text, not as markup

**Documentation**
- [ ] `README.md` explains what it is, how to run it, and how the five pipeline stages fit together
- [ ] `NOTES.md` has an appended section recording the working dependency versions and any decisions that departed from this spec

---

## 16. Working notes for the build

Build in this order and confirm each stage before moving on. Inspecting the output at every stage is the habit that separates a pipeline that works from one that appears to.

1. `config.py` — print every resolved value once and check it against `.env`
2. `ingestion.py` — read a real PDF, print page count and the first 300 characters of page 1
3. `chunking.py` — print chunk count, average length, and three sample chunks in full
4. `vectorstore.py` — index one document, print the stored count, run a search and print scores
5. `rag.py` — ask one question from the command line and read the answer and its citations
6. `schemas.py` + `main.py` — bring up the API, exercise every endpoint before touching the frontend
7. `static/` — build the interface last, against an API already known to work
8. Docs and the acceptance checklist

Never assume a stage worked because it did not raise. Print the output and look at it.
