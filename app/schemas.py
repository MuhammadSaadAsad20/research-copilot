"""
Pydantic models for the HTTP boundary.

The pipeline modules use plain dataclasses; these models exist only to describe
what goes in and out over HTTP, and to give FastAPI enough information to
document and validate the API. Keeping the two separate means the pipeline can
be used from a script without dragging web concerns along with it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# --- Requests --------------------------------------------------------------


class AskRequest(BaseModel):
    """A question, and optionally how many passages to retrieve for it."""

    question: str = Field(..., description="The question to answer.")
    top_k: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="How many passages to retrieve. Defaults to TOP_K.",
    )


# --- Responses -------------------------------------------------------------


class SourceModel(BaseModel):
    """One numbered citation, matching a passage given to the model."""

    number: int
    filename: str
    page: int
    score: float
    text: str


class AnswerResponse(BaseModel):
    question: str
    answer: str
    sources: list[SourceModel]


class DocumentModel(BaseModel):
    doc_id: str
    filename: str
    pages: int
    chunks: int


class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    pages: int
    chunks: int
    already_indexed: bool


class HealthResponse(BaseModel):
    ok: bool
    chat_model: str
    embedding_model: str
    documents: int
    chunks: int
    problems: list[str]


class ErrorResponse(BaseModel):
    """Every failure in this API has this shape, whatever the status code."""

    error: str
