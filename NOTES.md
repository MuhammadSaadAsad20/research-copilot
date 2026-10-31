# Notes

Running record of decisions, versions, and anything that departed from `SPEC.md`.
Append to this file; do not replace it.

---

## Build, 7 September 2026

### Environment

Built and verified on Windows 11, Python 3.14.6, in `venv/` at the project root.

The project root is `C:\Users\saada\OneDrive\Desktop\RAG\research-copilot`, not the
`Desktop\research-copilot` given in section 2. Nothing depends on the absolute path —
`BASE_DIR` is derived from `app/config.py`'s own location — so the difference is
cosmetic and was left alone.

### Pitfall 1 did not bite

`chromadb` **installed cleanly on Python 3.14** from a prebuilt `cp314` wheel. No
compilation, no fallback environment needed. This was the flagged risk in section 13,
so it is worth recording that it is not a problem with these versions:

```
chromadb==1.5.9
fastapi==0.141.1
langchain-text-splitters==1.1.2
openai==3.8.0
pypdf==6.17.0
python-dotenv==1.2.3
python-multipart==0.0.32
uvicorn==0.52.4
```

100 packages in total. `pip freeze` output is reproducible by rerunning
`.\venv\Scripts\python.exe -m pip freeze`.

Note that `openai==3.8.0` and `langchain-text-splitters==1.1.2` are both majors ahead
of what the reference code was presumably written against, and both worked unchanged.

### Fixes to the reference code

**`ingestion.py` — password-protected PDFs were not handled.** The shipped version
did this:

```python
try:
    reader.decrypt("")
except Exception as exc:
    raise IngestionError("This PDF is password protected...")
```

`pypdf.decrypt()` does not raise on a wrong password. It *returns* a falsy
`PasswordType.NOT_DECRYPTED`, so the `except` never fired, and the real failure
surfaced much later as an uncaught `FileNotDecryptedError` while iterating pages —
a 500, not the 422 the spec requires. Now the return value is checked as well, and
`list(reader.pages)` is wrapped so a malformed page tree also becomes an
`IngestionError`. Verified against a genuinely encrypted PDF.

**`rag.py` — the OpenAI client was rebuilt on every question.** `ask()` called
`OpenAI(api_key=...)` inline, opening a fresh connection pool per request. Replaced
with an `@lru_cache(maxsize=1)` `_openai()` that mirrors the one already in
`vectorstore.py`. The spec is silent on this specific point but states the principle
for `vectorstore.py`, so this makes the two modules consistent.

### Decisions where the spec was silent

**Validation order on upload.** Section 7 lists both 415/413 (bad request) and 503
(missing config) without saying which wins. Cheap request validation now runs first,
so uploading a `.txt` reports "that file is not a PDF" rather than "no API key",
which is the more useful message and is true regardless of configuration. The 503
gate sits immediately before the first call that actually needs the key.

**Duplicate uploads return 200, not 201.** The endpoint is declared `201 Created`,
but when `already_indexed` is true nothing was created, so the status is downgraded
per-response. The body shape is unchanged.

**Malformed request bodies return 400.** FastAPI's default for a validation error is
422, which this API reserves for "PDF unreadable or is a scan". A
`RequestValidationError` handler maps them to 400 instead, matching section 7.

### A conflict inside the spec

Section 8's layout sketch shows meta strings joined with middle dots
(`3 papers · 214 passages`, `page 3 · 0.61`), but the "Do not" list in the same
section explicitly forbids "meta strings joined with middle dots". The prohibition is
stated normatively and the sketch is illustrative, so the prohibition won. Those
strings now read `3 papers, 21 passages` and `page 3, match 0.21`.

### Console output is ASCII

`scripts/ingest.py` printed an em dash, which raises `UnicodeEncodeError` on a Windows
console using code page 437. All `print()` strings across the project are now ASCII.
The HTML and CSS still use proper typographic characters — those are UTF-8 and
declared as such.

`run.py` flushes stdout before handing control to uvicorn, so the URL is on screen
first rather than sitting in a block buffer behind uvicorn's stderr logging.

### What was verified, and what was not

Every stage in section 16 was run and its output inspected. What could **not** be
verified is anything requiring a live OpenAI key, because `.env` has none:

- Real embedding vectors, and therefore genuine semantic retrieval quality.
- Real `gpt-4o-mini` answers, and therefore whether citations point at pages that
  actually support the claim (section 15, "Retrieval quality").

To keep the rest honest rather than untested, only the two network calls were
stubbed — `vectorstore.embed_texts` with a deterministic hashed bag-of-words, and
`rag._openai()` with a canned completion. Everything else in those runs was the real
code: real Chroma reads and writes, real routes, real static files. The wiring is
therefore proven; the *quality* of retrieval is not, and cannot be until a key is
added.

Add a key to `.env` and rerun to close those two items:

```powershell
python scripts\ingest.py "C:\path\to\paper.pdf"
python run.py
```

### Chunk sizes observed

On the synthetic test papers, pages hold a single short paragraph, so each page
produced exactly one chunk averaging 394 characters — the splitter never had to
divide anything. On a dense page (~3000 characters, closer to a real two-column
paper) the same settings produced 5 chunks per page averaging 607 characters, none
over the 800 limit and none spanning a page boundary. Real papers should land in that
second range.

### Housekeeping

`reference/` is kept alongside the build. Section 3's tree does not list it because it
is input material rather than build output; the five files there are the originals
shipped with the spec, and `app/` now holds the corrected copies. Diffing the two
folders shows exactly what changed and why.

`data/uploads/` and `data/chroma/` were emptied of test artifacts after verification,
so the library starts empty.

### The dev/ harness

The verification scripts written during the build now live in `dev/`, with their test
fixtures in `dev/pdfs/`. Section 3's tree does not mention them because the spec is
silent on tests; they are kept because the acceptance checklist in section 15 is worth
being able to re-run, and because `dev/demo_server.py` makes it possible to show the
interface working without spending anything on the API.

Each script redirects `vectorstore.CHROMA_DIR` to its own throwaway database and
deletes it on exit, so `data/` is never touched. `python dev\acceptance.py` runs all
51 checks.
