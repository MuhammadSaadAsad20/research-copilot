"""
The web layer: routes, error handling, and serving the interface.

Every failure leaves this module as {"error": "<plain sentence>"} with a real
status code, so the frontend only ever has to understand one error shape.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.chunking import chunk_pages
from app.ingestion import IngestionError, document_id, read_pdf
from app.rag import GenerationError, ask
from app.schemas import (
    AnswerResponse,
    AskRequest,
    DocumentModel,
    HealthResponse,
    UploadResponse,
)
from app.vectorstore import (
    VectorStoreError,
    add_chunks,
    delete_document,
    document_exists,
    list_documents,
    total_chunks,
)

log = logging.getLogger("research_copilot")

app = FastAPI(
    title="Research Copilot",
    description="Ask questions about your own PDFs and get cited answers.",
    version="1.0.0",
)

config.ensure_dirs()

# The interface is plain files on disk. No build step, nothing to compile.
if config.STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


# --- Error handling --------------------------------------------------------
# Three handlers, one output shape. The frontend reads response.error and
# never has to guess which format it received.


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "Something went wrong."
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # A malformed body is the caller's mistake, so 400 rather than FastAPI's
    # default 422 — which this API reserves for PDFs it cannot read.
    return JSONResponse(
        status_code=400,
        content={"error": "That request was not in the expected format."},
    )


@app.exception_handler(Exception)
async def unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    # Log the detail for whoever is running the server; show the user a sentence.
    log.exception("Unhandled error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"error": "Something went wrong on the server. Check the terminal for details."},
    )


def _require_config() -> None:
    """Refuse work that needs the API key when the key is not there."""
    problems = config.missing_config()
    if problems:
        raise HTTPException(status_code=503, detail=" ".join(problems))


# --- Interface -------------------------------------------------------------


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    page = config.STATIC_DIR / "index.html"
    if not page.is_file():
        raise HTTPException(status_code=404, detail="The interface files are missing.")
    return FileResponse(page)


# --- API -------------------------------------------------------------------


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """
    Readiness and library stats.

    This endpoint never returns an error status — it is the diagnostic, so it
    has to work even when everything else is misconfigured.
    """
    problems = config.missing_config()
    documents = 0
    chunks = 0

    try:
        documents = len(list_documents())
        chunks = total_chunks()
    except Exception as exc:  # the database itself may be unavailable
        problems = problems + [f"The vector database could not be read: {exc}"]

    return HealthResponse(
        ok=not problems,
        chat_model=config.CHAT_MODEL,
        embedding_model=config.EMBEDDING_MODEL,
        documents=documents,
        chunks=chunks,
        problems=problems,
    )


@app.get("/api/documents", response_model=list[DocumentModel])
async def get_documents() -> list[DocumentModel]:
    try:
        return [DocumentModel(**entry) for entry in list_documents()]
    except VectorStoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/documents", response_model=UploadResponse, status_code=201)
async def upload_document(
    response: Response, file: UploadFile = File(...)
) -> UploadResponse:
    # Validate the request before checking server config, so a wrong file type
    # is reported as a wrong file type rather than as a missing API key.
    filename = (file.filename or "").strip() or "document.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=415,
            detail="That file is not a PDF. Upload a file ending in .pdf.",
        )

    payload = await file.read()

    if len(payload) > config.MAX_UPLOAD_BYTES:
        size_mb = len(payload) / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=(
                f"That file is {size_mb:.1f} MB, over the "
                f"{config.MAX_UPLOAD_MB} MB limit."
            ),
        )

    # Check the magic bytes too: a renamed .txt would pass the extension test.
    if not payload.startswith(b"%PDF"):
        raise HTTPException(
            status_code=415,
            detail="That file is named .pdf but is not a PDF inside.",
        )

    doc_id = document_id(payload)

    # Same content, already indexed. Re-embedding it would cost money and
    # change nothing, so report the existing counts instead.
    try:
        if document_exists(doc_id):
            existing = next(
                (d for d in list_documents() if d["doc_id"] == doc_id), None
            )
            # Nothing was created, so 201 would be a lie.
            response.status_code = 200
            return UploadResponse(
                doc_id=doc_id,
                filename=existing["filename"] if existing else filename,
                pages=existing["pages"] if existing else 0,
                chunks=existing["chunks"] if existing else 0,
                already_indexed=True,
            )
    except VectorStoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Everything past here needs the embedding API.
    _require_config()

    stored_path = config.UPLOAD_DIR / f"{doc_id}.pdf"
    stored_path.write_bytes(payload)

    try:
        pages = read_pdf(stored_path)
    except IngestionError as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    chunks = chunk_pages(pages, doc_id, filename)
    if not chunks:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=422,
            detail="That PDF had no passages long enough to index.",
        )

    try:
        stored = add_chunks(chunks)
    except VectorStoreError as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return UploadResponse(
        doc_id=doc_id,
        filename=filename,
        pages=len(pages),
        chunks=stored,
        already_indexed=False,
    )


@app.delete("/api/documents/{doc_id}")
async def remove_document(doc_id: str) -> dict:
    try:
        if not document_exists(doc_id):
            raise HTTPException(
                status_code=404, detail="That document is not in the library."
            )
        delete_document(doc_id)
    except VectorStoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    (config.UPLOAD_DIR / f"{doc_id}.pdf").unlink(missing_ok=True)
    return {"doc_id": doc_id, "removed": True}


@app.post("/api/ask", response_model=AnswerResponse)
async def ask_question(request: AskRequest) -> AnswerResponse:
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Type a question first.")

    _require_config()

    try:
        answer = ask(question, request.top_k)
    except (GenerationError, VectorStoreError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return AnswerResponse(**answer.to_dict())
