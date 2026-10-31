"""
A guided tour of stages 3, 4 and 5, using the real code and real API calls.

    python dev\\learn_stages.py

Everything here runs against a throwaway database in dev/, so your real library
in data/ is untouched. It makes roughly 20 small embedding calls and one chat
call - well under a cent in total.

Read the code alongside the output. Each lesson is deliberately short.
"""

import math
import shutil
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from app import config, rag
from app import vectorstore as vs
from app.chunking import chunk_pages
from app.ingestion import document_id, read_pdf

# Throwaway database, so data/ is never touched.
DB = HERE / "chroma_learn"
if DB.exists():
    shutil.rmtree(DB)
vs.CHROMA_DIR = DB
config.UPLOAD_DIR = HERE / "uploads_test"
config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def title(n, text):
    print()
    print("=" * 78)
    print(f"  LESSON {n}: {text}")
    print("=" * 78)


def wrap(text, indent="    "):
    print(textwrap.fill(text, width=74, initial_indent=indent,
                        subsequent_indent=indent))


# ---------------------------------------------------------------------------
title(1, "What an embedding actually is")

vec = vs.embed_texts(["The Transformer relies entirely on self-attention."])[0]

print(f"\n  Input : 'The Transformer relies entirely on self-attention.'")
print(f"  Output: a list of {len(vec)} numbers\n")
print("  The first 8 of them:")
print("   ", [round(x, 4) for x in vec[:8]])
print("  The last 4:")
print("   ", [round(x, 4) for x in vec[-4:]])

magnitude = math.sqrt(sum(x * x for x in vec))
print(f"\n  Length (magnitude) of this vector: {magnitude:.6f}")
wrap("OpenAI returns unit vectors - length exactly 1.0. Every embedding sits "
     "on the surface of a sphere in 1536-dimensional space. Only DIRECTION "
     "carries meaning, not distance from the origin. That is why cosine "
     "(an angle) is the right way to compare them.")


# ---------------------------------------------------------------------------
title(2, "Meaning, not words")


def cosine(a, b):
    """For unit vectors this is just the dot product."""
    return sum(x * y for x, y in zip(a, b))


anchor = "antimicrobial resistance in livestock farming"
same_meaning = "drug-resistant bacteria spreading on farms"
shared_words = "resistance training for livestock farmers"
unrelated = "the best way to cook a mushroom risotto"

texts = [anchor, same_meaning, shared_words, unrelated]
vecs = vs.embed_texts(texts)


def overlap(a, b):
    wa, wb = set(a.lower().split()), set(b.lower().split())
    return len(wa & wb)


print(f"\n  Anchor: '{anchor}'\n")
print(f"  {'candidate':<46}{'shared words':>13}{'similarity':>12}")
print("  " + "-" * 71)
for text, v in zip(texts[1:], vecs[1:]):
    print(f"  {text:<46}{overlap(anchor, text):>13}{cosine(vecs[0], v):>12.3f}")

print()
wrap("Look at the middle row. It shares THREE words with the anchor and still "
     "scores lower than the row that shares NONE. Keyword search would rank "
     "them the other way round. This is the whole reason embeddings are worth "
     "the trouble: the model compares meaning, not spelling.")


# ---------------------------------------------------------------------------
title(3, "Storing chunks - what Chroma actually holds")

pdf = HERE / "pdfs" / "lantern.pdf"
doc_id = document_id(pdf.read_bytes())
pages = read_pdf(pdf)
chunks = chunk_pages(pages, doc_id, pdf.name)

print(f"\n  {pdf.name}: {len(pages)} pages -> {len(chunks)} chunks")
print(f"  Embedding them in batches of {config.EMBED_BATCH_SIZE}...")

stored = vs.add_chunks(chunks)
print(f"  Stored: {stored}\n")

raw = vs._collection().get(ids=[chunks[0].chunk_id],
                           include=["documents", "metadatas", "embeddings"])
print("  One row of the database, in full:\n")
print(f"    id        : {raw['ids'][0]}")
print(f"    metadata  : {raw['metadatas'][0]}")
emb = raw["embeddings"][0]
print(f"    embedding : [{emb[0]:.4f}, {emb[1]:.4f}, ... ] ({len(emb)} numbers)")
doc = raw["documents"][0]
print(f"    document  : {doc[:70]}...")

print()
wrap("Four things per row: a unique id, the vector used for searching, the "
     "ORIGINAL TEXT (this is what gets shown to the model later - the vector "
     "is only for finding it), and metadata carrying the filename and page "
     "number that make a citation possible.")
print()
wrap("Metadata values must be str, int, float or bool. A None or a list "
     "raises. That is why page and index are cast to int explicitly - it is "
     "pitfall 2 in the spec.")


# ---------------------------------------------------------------------------
title(4, "Search - and the trap in the numbers")

question = "How does the model avoid recurrence?"
qvec = vs.embed_texts([question])[0]

print(f"\n  Question: '{question}'")
wrap("The question is embedded with the SAME model as the chunks. Two "
     "different models produce incompatible number spaces, and the search "
     "would return noise.", indent="  ")

results = vs._collection().query(
    query_embeddings=[qvec], n_results=3,
    include=["documents", "metadatas", "distances"],
)

print("\n  Chroma's raw reply is one list PER QUERY. We sent one query, so:")
print(f"    results['distances']    -> a list of {len(results['distances'])} item(s)")
print(f"    results['distances'][0] -> the {len(results['distances'][0])} actual distances")
wrap("Forgetting that [0] is pitfall 3, and produces a confusing zip of "
     "nested lists.", indent="  ")

print("\n  Raw distances, and the score we show the user:\n")
print(f"  {'page':>5}{'distance':>11}{'1 - distance':>15}   text")
print("  " + "-" * 72)
for d, m, t in zip(results["distances"][0], results["metadatas"][0],
                   results["documents"][0]):
    print(f"  {m['page']:>5}{d:>11.4f}{max(0.0, 1.0 - d):>15.3f}   {t[:32]}...")

print()
wrap("With cosine space, Chroma returns DISTANCE, where 0.0 means identical. "
     "Shown raw, a perfect match looks like a zero score - the numbers read "
     "backwards. Converting with 1 - distance flips it so bigger is better. "
     "That is pitfall 4.")

print("\n  Now through the real search() function, which does all of that:\n")
for r in vs.search(question, 3):
    print(f"    score {r.score:<7} {r.filename}  page {r.page}")


# ---------------------------------------------------------------------------
title(5, "The prompt - exactly what the model receives")

passages = vs.search(question, config.TOP_K)
context = rag._build_context(passages)
user_prompt = (
    f"{context}\n\n---\nQuestion: {question}\n\n"
    "Answer using only the passages above, citing each claim by number."
)

print("\n  ---------- SYSTEM MESSAGE ----------")
for line in rag.SYSTEM_PROMPT.split("\n"):
    print(f"  {line}")

print("\n  ---------- USER MESSAGE ----------")
shown = user_prompt if len(user_prompt) < 1800 else user_prompt[:1800] + "\n  [...truncated for display...]"
for line in shown.split("\n"):
    print(f"  {line}")

print("\n  ---------- END ----------\n")
wrap(f"That is the ENTIRE knowledge the model has for this question. "
     f"{len(passages)} passages, about {len(user_prompt)} characters. It has "
     "never seen the other pages of the paper, and it cannot look them up.")
print()
wrap("Notice the numbering. Passage [1] in this prompt becomes source 1 in "
     "the response, which becomes note 1 in the margin. That single "
     "correspondence is what makes a clickable citation possible.")


# ---------------------------------------------------------------------------
title(6, "Generation - one real call")

answer = rag.ask(question, top_k=config.TOP_K)

print(f"\n  Model: {config.CHAT_MODEL}, temperature 0.1\n")
for line in textwrap.wrap(answer.answer, width=74):
    print(f"  {line}")

print("\n  Sources it was given:\n")
for s in answer.sources:
    print(f"    [{s.number}] {s.filename}  page {s.page}  score {s.score}")

print()
wrap("Every [n] in that answer maps to a row above. The model could not "
     "invent a [9], because there is no passage 9 - and the frontend refuses "
     "to linkify a number outside the range anyway.")


# ---------------------------------------------------------------------------
title(7, "Proving it will not answer from memory")

off_topic = "What is the recommended daily intake of vitamin D?"
print(f"\n  Question: '{off_topic}'")
wrap("gpt-4o-mini certainly knows this. But the library only contains a fake "
     "paper about sequence models, so the retrieved passages will be "
     "irrelevant, and rule 3 tells it to say so rather than answer.",
     indent="  ")

off = rag.ask(off_topic, top_k=3)
print()
for line in textwrap.wrap(off.answer, width=74):
    print(f"  {line}")

print("\n  Passages it was handed anyway (search always returns SOMETHING):\n")
for s in off.sources:
    print(f"    [{s.number}] page {s.page}  score {s.score}")
print()
wrap("This is the important bit. Retrieval has no idea the question is "
     "off-topic - it dutifully returns the 5 least-bad matches, with low "
     "scores. The REFUSAL comes from the prompt, not the search. Retrieval "
     "and instruction are two separate safety layers, and you need both.")

shutil.rmtree(DB, ignore_errors=True)
shutil.rmtree(HERE / "uploads_test", ignore_errors=True)
print("\n" + "=" * 78)
print("  Done. Throwaway database removed; data/ untouched.")
print("=" * 78)
