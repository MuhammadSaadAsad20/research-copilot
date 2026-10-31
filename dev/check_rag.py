"""Exercise rag.ask() without an OpenAI key.

Only the chat call is stubbed. The prompt assembly, passage numbering and
Answer/Source shaping are the real code.
"""
import sys
from pathlib import Path

# Run from anywhere: put the project root on the import path.
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import sys
from types import SimpleNamespace

from app import rag
from app.vectorstore import Retrieved

CAPTURED = {}


class FakeCompletions:
    def create(self, **kwargs):
        CAPTURED.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(
                content="It replaces recurrence with gated retrieval [1], which gives "
                        "every position a constant path length to every other [2]."
            ))]
        )


class FakeClient:
    chat = SimpleNamespace(completions=FakeCompletions())


PASSAGES = [
    Retrieved(text="The Lantern model removes the recurrent connection altogether.",
              doc_id="aaa", filename="lantern.pdf", page=3, score=0.61),
    Retrieved(text="Constant path length is what makes long-range dependencies learnable.",
              doc_id="aaa", filename="lantern.pdf", page=5, score=0.58),
]

print("--- empty library ---")
rag.total_chunks = lambda: 0
a = rag.ask("anything at all")
print("  answer :", a.answer)
print("  sources:", a.sources)
print("  no exception raised, friendly answer:", a.sources == [])
print()

print("--- library has content but nothing matches ---")
rag.total_chunks = lambda: 42
rag.search = lambda q, k: []
a = rag.ask("something unrelated")
print("  answer :", a.answer)
print("  sources:", a.sources)
print()

print("--- missing key ---")
rag.search = lambda q, k: PASSAGES
rag.OPENAI_API_KEY = ""
try:
    rag.ask("how does it avoid recurrence")
    print("  NO ERROR (unexpected)")
except rag.GenerationError as e:
    print("  GenerationError:", e)
print()

print("--- empty question ---")
try:
    rag.ask("   ")
except rag.GenerationError as e:
    print("  GenerationError:", e)
print()

print("--- full path with stubbed model ---")
rag.OPENAI_API_KEY = "sk-test"
rag._openai.cache_clear()
rag._openai = lambda: FakeClient()
answer = rag.ask("how does it avoid recurrence", top_k=2)

print("  question:", answer.question)
print("  answer  :", answer.answer)
print("  sources :")
for s in answer.sources:
    print(f"    [{s.number}] {s.filename} page {s.page} score {s.score}")
print()
print("  model    :", CAPTURED.get("model"))
print("  temperature:", CAPTURED.get("temperature"))
msgs = CAPTURED.get("messages", [])
print("  roles    :", [m["role"] for m in msgs])
print()
print("--- the user message sent to the model ---")
print(msgs[1]["content"])
print("--- end ---")
print()

sysmsg = msgs[0]["content"]
print("system prompt starts:", sysmsg.split("\n")[0])
print("system prompt has 5 numbered rules:",
      all(f"\n{n}." in sysmsg for n in range(1, 6)))
print()

print("--- alignment checks (this is what makes the margin work) ---")
ok_align = all(
    answer.sources[i].filename == PASSAGES[i].filename
    and answer.sources[i].page == PASSAGES[i].page
    and answer.sources[i].text == PASSAGES[i].text
    for i in range(len(PASSAGES))
)
print("  source N == passage N     :", ok_align)
print("  numbering is 1-based      :", [s.number for s in answer.sources] == [1, 2])
print("  prompt numbers match      :",
      '[1] From "lantern.pdf", page 3:' in msgs[1]["content"]
      and '[2] From "lantern.pdf", page 5:' in msgs[1]["content"])
d = answer.to_dict()
print("  to_dict keys              :", sorted(d.keys()))
print("  to_dict sources are dicts :", isinstance(d["sources"][0], dict))
print()
print("rag OK")
