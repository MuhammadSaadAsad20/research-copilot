"""
Steps 4 and 5 of the pipeline: retrieve, then generate.

This is where "retrieval-augmented generation" earns its name. We never ask the
language model what it knows. We find the passages that actually answer the
question, hand them over as the only permitted source, and ask it to write an
answer that points back at them.

The numbering matters. Passage 1 in the prompt is source 1 in the response, so
a [1] in the answer text can be linked to a real page in a real document.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from openai import OpenAI

from app.config import CHAT_MODEL, OPENAI_API_KEY, TOP_K
from app.vectorstore import Retrieved, VectorStoreError, search, total_chunks


class GenerationError(Exception):
    """Raised when the language model cannot produce an answer."""


@dataclass
class Source:
    """One numbered citation shown alongside the answer."""

    number: int
    filename: str
    page: int
    score: float
    text: str


@dataclass
class Answer:
    """The complete result of asking a question."""

    question: str
    answer: str
    sources: list[Source]

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "sources": [asdict(source) for source in self.sources],
        }


SYSTEM_PROMPT = """You are a research assistant. You answer questions about a \
specific set of documents, and you only use what those documents say.

Rules you always follow:
1. Use only the numbered passages provided. Never add outside knowledge, even \
if you are confident it is correct.
2. Cite the passage number in square brackets after every claim, like [1] or \
[2][4]. Every factual sentence needs at least one citation.
3. If the passages do not answer the question, say so plainly in one sentence \
and stop. Do not speculate or pad.
4. Be direct and specific. Lead with the answer rather than restating the \
question. Quote from the passages only when the exact wording matters.
5. Write in plain prose. Use a short list only when the answer really is a set \
of parallel items."""


def _build_context(passages: list[Retrieved]) -> str:
    """Format retrieved passages as a numbered block for the prompt."""
    blocks = []
    for number, passage in enumerate(passages, start=1):
        blocks.append(
            f"[{number}] From \"{passage.filename}\", page {passage.page}:\n"
            f"{passage.text}"
        )
    return "\n\n".join(blocks)


def ask(question: str, top_k: int | None = None) -> Answer:
    """Answer a question against the stored documents."""
    question = question.strip()
    if not question:
        raise GenerationError("Ask a question first.")

    if total_chunks() == 0:
        return Answer(
            question=question,
            answer="There are no documents in the library yet. Add a PDF and ask again.",
            sources=[],
        )

    passages = search(question, top_k or TOP_K)
    if not passages:
        return Answer(
            question=question,
            answer="Nothing in the library matched that question.",
            sources=[],
        )

    if not OPENAI_API_KEY:
        raise GenerationError(
            "OPENAI_API_KEY is not set. Add it to the .env file and restart."
        )

    user_prompt = (
        f"{_build_context(passages)}\n\n"
        f"---\n"
        f"Question: {question}\n\n"
        f"Answer using only the passages above, citing each claim by number."
    )

    try:
        response = OpenAI(api_key=OPENAI_API_KEY).chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            # Low temperature keeps the model close to the source text instead
            # of paraphrasing creatively, which is what we want for research.
            temperature=0.1,
        )
    except Exception as exc:
        raise GenerationError(f"The language model request failed: {exc}") from exc

    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise GenerationError("The language model returned an empty answer.")

    sources = [
        Source(
            number=number,
            filename=passage.filename,
            page=passage.page,
            score=passage.score,
            text=passage.text,
        )
        for number, passage in enumerate(passages, start=1)
    ]

    return Answer(question=question, answer=text, sources=sources)


__all__ = ["ask", "Answer", "Source", "GenerationError", "VectorStoreError"]
