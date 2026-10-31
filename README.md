# Research copilot

Drop research PDFs into a local web app, ask questions in plain English, and get
answers written only from those PDFs — with every claim carrying a numbered citation
that resolves to a real page in a real document.

The citations are the point. They are not tucked into a collapsed panel at the bottom;
they live in a margin beside the answer, numbered and always visible. Clicking a
superscript marker in the prose jumps to the passage it came from, and hovering a
margin note highlights every marker that points at it.

Everything runs on your machine. The only thing that leaves it is the text of your
questions and the retrieved passages, which go to OpenAI to be embedded and answered.

---

## Getting started

You need Python 3.12 or newer and an OpenAI API key.

```powershell
cd research-copilot
py -3.14 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Put your key in `.env` at the project root:

```
OPENAI_API_KEY=sk-your-key-here
```

Then start it:

```powershell
python run.py
```

Open <http://127.0.0.1:8000>, click **Add a PDF**, and ask something once it has been
read. A short paper takes a few seconds; a 200-page one takes tens of seconds, and the
button says "Reading…" while it works.

If the key is missing the app still starts — it shows the problem in a banner and
disables the question box, rather than refusing to boot.

### Indexing without the browser

```powershell
python scripts\ingest.py "C:\path\to\paper.pdf"
```

Prints the page count, chunk count, average chunk length and time taken. Useful when
you want to know whether a problem is in the pipeline or in the interface.

---

## How it works

Five stages. Each is a separate module, and each can be run and inspected on its own —
which is the whole reason the pipeline is split this way.

```
PDF file
  │
  ├─ 1. ingestion.py    pypdf reads each page. The text is cleaned: words
  │                     hyphenated across a line break are rejoined, wrapped
  │                     lines are collapsed back into paragraphs, whitespace is
  │                     squeezed. Page numbers are kept throughout.
  │
  ├─ 2. chunking.py     Each page is split on its own into ~800-character chunks
  │                     with 150 characters of overlap. Splitting per page rather
  │                     than across the whole document costs a little context at
  │                     page boundaries and buys exact citations: every chunk
  │                     belongs to exactly one page, so a citation can name it.
  │
  ├─ 3. vectorstore.py  Chunks are embedded in batches of 64 and stored in
  │                     ChromaDB with cosine distance, alongside their text and
  │                     metadata.
  │
  ├─ 4. vectorstore.py  A question is embedded, and the nearest 5 chunks come
  │       (search)      back. Cosine *distance* is converted to a 0–1 score where
  │                     higher is better, so the numbers read the way you expect.
  │
  └─ 5. rag.py          Those chunks are numbered and handed to the chat model as
                        the only permitted source. It writes an answer citing
                        [1], [2]. Passage N in the prompt is source N in the
                        response — that alignment is what makes the margin work.
```

### Why retrieval at all

The model is never asked what it knows. It is given the passages that actually answer
the question and told to use nothing else, which is what makes an answer checkable: if
a claim carries `[2]`, you can read source 2 in the margin and decide for yourself
whether it says what the answer claims.

The system prompt makes three demands that matter — use only the passages provided,
cite every factual sentence, and say plainly when the passages do not answer the
question rather than padding or speculating.

### Documents are identified by content

`doc_id` is a hash of the file's bytes, not its name. Upload the same paper twice under
different names and the second upload is recognised as a duplicate: nothing is
re-embedded, and no second row appears in the library.

---

## Project layout

```
research-copilot/
├── .env                  your API key (not committed)
├── .env.example          the same keys with no values
├── requirements.txt
├── run.py                start the app
├── app/
│   ├── config.py         every tunable value, read from .env
│   ├── ingestion.py      PDF  -> pages of clean text
│   ├── chunking.py       pages -> chunks
│   ├── vectorstore.py    chunks -> embeddings -> ChromaDB, and search
│   ├── rag.py            retrieve + generate a cited answer
│   ├── schemas.py        request/response models
│   └── main.py           routes and error handling
├── static/               the interface: one HTML file, one CSS file, one JS file
├── scripts/ingest.py     index a PDF from the command line
└── data/
    ├── uploads/          the original PDFs
    └── chroma/           the vector database
```

There is **no build step**. The frontend is hand-written HTML, CSS and vanilla
JavaScript served directly by FastAPI. No Node, no npm, no bundler — nothing to
install beyond the Python dependencies, and nothing to break on a machine that has
never had a JavaScript toolchain on it.

---

## The API

Everything the interface does is available directly.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | The interface |
| `GET` | `/api/health` | Readiness and library stats |
| `GET` | `/api/documents` | List indexed documents |
| `POST` | `/api/documents` | Upload and index a PDF (`multipart/form-data`, field `file`) |
| `DELETE` | `/api/documents/{doc_id}` | Remove a document and its vectors |
| `POST` | `/api/ask` | Ask a question |

`GET /api/health` is the diagnostic and never returns an error status — when something
is misconfigured it returns `ok: false` with the reasons in `problems`.

Every failure, whatever the cause, has the same shape:

```json
{ "error": "That file is not a PDF. Upload a file ending in .pdf." }
```

with a real status code: 400 for a bad request, 404 for an unknown document, 413 for an
oversized upload, 415 for a non-PDF, 422 for a PDF that cannot be read, 502 when
OpenAI fails, 503 when the key is missing.

Interactive documentation is at <http://127.0.0.1:8000/docs> while the app is running.

---

## Configuration

All of it lives in `app/config.py` and can be overridden in `.env`.

| Setting | Default | What it does |
|---|---|---|
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Turns text into vectors |
| `CHAT_MODEL` | `gpt-4o-mini` | Writes the answer |
| `CHUNK_SIZE` | `800` | Characters per chunk |
| `CHUNK_OVERLAP` | `150` | Overlap between neighbouring chunks |
| `MIN_CHUNK_CHARS` | `60` | Chunks shorter than this are dropped |
| `TOP_K` | `5` | Passages retrieved per question |
| `EMBED_BATCH_SIZE` | `64` | Texts per embedding request |
| `MAX_UPLOAD_MB` | `25` | Upload size limit |

---

## Known limits

- **Scanned PDFs will not work.** If a page is an image, there is no text to extract.
  The app says so and names OCR as the fix, but does not do OCR.
- **No conversation memory.** Each question is answered on its own; there are no
  follow-ups that refer back to the last answer.
- **Retrieval is a single semantic search.** No reranking, no keyword hybrid, no query
  rewriting.

---

## Where this could go next

Deliberately left out to keep the failure surface small. In rough order of value:

- Streaming the answer as it is written, instead of a loading state.
- Reranking or hybrid keyword + semantic search, for better retrieval on questions
  that hinge on a specific term.
- Follow-up questions with memory of the previous answer.
- OCR for scanned PDFs.
- Multi-user support, with accounts and per-user libraries.
