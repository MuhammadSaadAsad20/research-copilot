"""
Build the "Stages 3-5 explained" reference PDF.

    python dev\\build_lesson_pdf.py

Output: RAG-stages-3-5-explained.pdf in the project root.
Colours match the app's own design system.
"""

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph,
    Preformatted, Spacer, Table, TableStyle,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "RAG-stages-3-5-explained.pdf"

# The app's palette (static/style.css).
INK = colors.HexColor("#131A2A")
INK_SOFT = colors.HexColor("#56607A")
RULE = colors.HexColor("#D8DDE6")
PEN = colors.HexColor("#2B4ACB")
PEN_WASH = colors.HexColor("#E8ECFB")
PAPER = colors.HexColor("#F2F4F7")

styles = getSampleStyleSheet()

S = {
    "title": ParagraphStyle(
        "title", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=25, leading=30, textColor=INK, spaceAfter=5),
    "subtitle": ParagraphStyle(
        "subtitle", parent=styles["Normal"], fontName="Helvetica",
        fontSize=12.5, leading=17, textColor=INK_SOFT, spaceAfter=3),
    "meta": ParagraphStyle(
        "meta", parent=styles["Normal"], fontName="Helvetica",
        fontSize=8.5, leading=12, textColor=INK_SOFT),
    "h1": ParagraphStyle(
        "h1", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=17, leading=21, textColor=PEN, spaceBefore=20, spaceAfter=8),
    "h2": ParagraphStyle(
        "h2", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=11.5, leading=15, textColor=INK, spaceBefore=13, spaceAfter=5),
    "body": ParagraphStyle(
        "body", parent=styles["Normal"], fontName="Helvetica",
        fontSize=9.7, leading=14.6, textColor=INK, alignment=TA_JUSTIFY,
        spaceAfter=7),
    "bullet": ParagraphStyle(
        "bullet", parent=styles["Normal"], fontName="Helvetica",
        fontSize=9.7, leading=14.2, textColor=INK,
        leftIndent=13, bulletIndent=3, spaceAfter=4),
    "code": ParagraphStyle(
        "code", parent=styles["Normal"], fontName="Courier",
        fontSize=8.3, leading=11.4, textColor=INK),
    "note": ParagraphStyle(
        "note", parent=styles["Normal"], fontName="Helvetica",
        fontSize=9.4, leading=14, textColor=INK, alignment=TA_JUSTIFY),
    "cellh": ParagraphStyle(
        "cellh", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=8.6, leading=11.5, textColor=INK),
    "cell": ParagraphStyle(
        "cell", parent=styles["Normal"], fontName="Helvetica",
        fontSize=8.6, leading=11.5, textColor=INK),
}

story = []


def h1(t):
    story.append(Paragraph(t, S["h1"]))


def h2(t):
    story.append(Paragraph(t, S["h2"]))


def p(t):
    story.append(Paragraph(t, S["body"]))


def bullets(items):
    for it in items:
        story.append(Paragraph(it, S["bullet"], bulletText="•"))
    story.append(Spacer(1, 4))


def code(text):
    text = text.strip("\n")
    block = Preformatted(text, S["code"])
    tbl = Table([[block]], colWidths=[165 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PAPER),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 9))


def note(text):
    """A highlighted takeaway box."""
    para = Paragraph(text, S["note"])
    tbl = Table([[para]], colWidths=[165 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PEN_WASH),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, PEN),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(KeepTogether(tbl))
    story.append(Spacer(1, 10))


def table(header, rows, widths):
    data = [[Paragraph(c, S["cellh"]) for c in header]]
    for r in rows:
        data.append([Paragraph(c, S["cell"]) for c in r])
    tbl = Table(data, colWidths=widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PAPER),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK_SOFT),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, RULE),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    # Small tables should never split across a page and orphan a row from
    # its header.
    story.append(KeepTogether(tbl))
    story.append(Spacer(1, 11))


# ===========================================================================
# Cover
# ===========================================================================
story.append(Spacer(1, 6))
story.append(Paragraph("Retrieval-Augmented Generation", S["title"]))
story.append(Paragraph("Stages 3 to 5: Embedding, Search, and Generation",
                       S["subtitle"]))
story.append(Spacer(1, 5))
story.append(Paragraph(
    "A working explanation of how the Research Copilot turns a PDF into "
    "searchable meaning, finds the right passages for a question, and writes "
    "an answer that can be checked against its sources.", S["meta"]))
story.append(Spacer(1, 9))

hr = Table([[""]], colWidths=[165 * mm], rowHeights=[1])
hr.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 1.1, PEN)]))
story.append(hr)
story.append(Spacer(1, 12))

p("Every number, score and output quoted in this document came from a real "
  "run against the live OpenAI API, not from an illustration. You can "
  "reproduce all of it with <font face='Courier' size='9'>python "
  "dev\\learn_stages.py</font>.")

note("<b>The one idea to hold onto.</b> The language model never reads your "
     "document. The paper is read once at upload time and filed away as "
     "numbers. When you ask a question, the model receives roughly five short "
     "excerpts and nothing else. Almost every behaviour of this system "
     "follows from that single fact.")

# ===========================================================================
h1("Stage 3 &nbsp;&middot;&nbsp; Embedding and storage")

h2("What an embedding actually is")
p("An embedding is a function that turns text into a fixed-length list of "
  "numbers. The model used here, <b>text-embedding-3-small</b>, always "
  "returns <b>1536 numbers</b> &mdash; whether you feed it a single word or "
  "800 characters.")

code("""Input : 'The Transformer relies entirely on self-attention.'
Output: a list of 1536 numbers

First 8 : [0.0146, 0.0328, -0.004, -0.0116, 0.0072, -0.0208, 0.0324, 0.0539]
Magnitude: 0.999885""")

p("That magnitude is not a coincidence. OpenAI returns <b>unit vectors</b>: "
  "every embedding has a length of 1.0, so they all sit on the surface of a "
  "sphere in 1536-dimensional space. Only the <i>direction</i> carries "
  "meaning. That is precisely why the right way to compare two embeddings is "
  "an angle &mdash; a cosine &mdash; rather than a straight-line distance.")

p("Individual numbers cannot be interpreted. Dimension 400 does not mean "
  "&ldquo;is about biology&rdquo;. Meaning is spread across all 1536 in a way "
  "no human reads directly. All that matters is that similar meanings point "
  "in similar directions.")

h2("Meaning, not words")
p("The model was trained so that text appearing in similar contexts receives "
  "similar vectors. Nobody labelled anything by hand; the effect fell out of "
  "the training objective. Here is that effect measured against the anchor "
  "phrase <i>&ldquo;antimicrobial resistance in livestock farming&rdquo;</i>:")

table(["Candidate phrase", "Words shared<br/>with anchor", "Similarity"],
      [["drug-resistant bacteria spreading on farms", "<b>0</b>", "<b>0.722</b>"],
       ["resistance training for livestock farmers", "2", "0.614"],
       ["the best way to cook a mushroom risotto", "0", "0.135"]],
      [92 * mm, 36 * mm, 37 * mm])

note("Read the first two rows again. The phrase sharing <b>no words at all</b> "
     "scores higher than the phrase sharing two. A keyword search would rank "
     "them the other way round. That inversion is the entire justification "
     "for embeddings: a reader asking &ldquo;why are farm antibiotics a "
     "problem?&rdquo; still finds the right passage, even though the paper "
     "never uses their words.")

h2("Batching, and the order trap")
p("Chunks are embedded 64 at a time. Each API request has a token ceiling, "
  "and one round trip for 64 items is far faster than 64 round trips. A "
  "70-page paper producing about 650 chunks becomes roughly 11 requests.")

code("""ordered = sorted(response.data, key=lambda item: item.index)""")

p("The API already returns results in input order, yet the code sorts by "
  "index anyway. This is the cheapest insurance in the codebase. If that "
  "ordering ever changed silently, every chunk would be stored against the "
  "wrong vector. The library would still appear to work, returning confident, "
  "well-formatted and completely wrong citations. Sorting makes the guarantee "
  "explicit rather than assumed.")

h2("What the database actually holds")
code("""id        : b09d986bef0cc99c:0
metadata  : {'filename': 'lantern.pdf', 'doc_id': 'b09d986bef0cc99c',
             'page': 1, 'index': 0}
embedding : [-0.0180, -0.0033, ... ]  (1536 numbers)
document  : Abstract We introduce the Lantern architecture...""")

p("Four fields, and the division of labour between them is the point:")
bullets([
    "<b>embedding</b> &mdash; used <i>only</i> to find the row. Never shown to "
    "anyone.",
    "<b>document</b> &mdash; the original text. This is what eventually "
    "reaches the language model.",
    "<b>metadata</b> &mdash; filename and page number. <b>This is what makes "
    "citation possible.</b> Without it you would retrieve excellent text and "
    "have no idea where it came from.",
    "<b>id</b> &mdash; formed as <font face='Courier' size='9'>"
    "{doc_id}:{index}</font>, unique across the whole database.",
])
p("Chroma restricts metadata values to <font face='Courier' size='9'>str</font>, "
  "<font face='Courier' size='9'>int</font>, <font face='Courier' size='9'>"
  "float</font> or <font face='Courier' size='9'>bool</font>. A None, a list "
  "or a Path raises an error, which is why page and index are cast to integers "
  "explicitly.")

h2("Why upsert rather than add")
p("Because the chunk id derives from a hash of the file's contents, "
  "re-indexing the same document <i>overwrites its own rows</i> instead of "
  "creating duplicates. Combined with the duplicate check that happens before "
  "any embedding is requested, that is belt and braces against paying twice "
  "for the same paper.")

h2("Why search stays fast")
p("Chroma does not compare your question against all 650 vectors one at a "
  "time. It builds an <b>HNSW index</b> (Hierarchical Navigable Small World) "
  "&mdash; a graph that can be navigated toward the nearest neighbours "
  "without visiting everything. The trade-off is that results are "
  "<i>approximate</i>: occasionally the true nearest neighbour is missed. At "
  "this scale that is irrelevant, but it is the reason vector search remains "
  "fast at millions of documents.")

h2("Why the API clients are built lazily")
code("""@lru_cache(maxsize=1)
def _openai() -> OpenAI:
    ...""")
p("The client is created on first use and then cached. This buys one "
  "connection pool instead of one per request, and &mdash; more importantly "
  "&mdash; lets the application start without an API key. Were the client "
  "built at import time, a missing key would crash the server on boot rather "
  "than displaying a readable message in the interface.")

# ===========================================================================
h1("Stage 4 &nbsp;&middot;&nbsp; Search")

h2("The same-model rule")
p("The question is embedded with <b>exactly the same model</b> as the chunks. "
  "This is not a preference. Two different embedding models produce entirely "
  "unrelated coordinate systems; mixing them does not merely degrade results, "
  "it returns noise. Changing the embedding model means re-indexing "
  "everything.")

h2("One list per query")
code("""results['distances']     ->  a list of 1 item
results['distances'][0]  ->  the 3 actual distances""")
p("Chroma's query function accepts many query vectors at once, so it returns "
  "one list <i>per query</i>. Since a single question is sent, the real "
  "results live at index zero. Omitting that index produces a confusing zip "
  "of nested lists rather than an obvious error.")

h2("Distance runs backwards")
table(["Page", "Raw distance", "1 &minus; distance", "Passage"],
      [["3", "0.5366", "<b>0.463</b>", "The Lantern model removes the recurrent connection..."],
       ["2", "0.5401", "0.460", "1 Introduction Recurrent networks process a sequence..."],
       ["1", "0.5579", "0.442", "Abstract We introduce the Lantern architecture..."]],
      [14 * mm, 26 * mm, 27 * mm, 98 * mm])

p("In cosine space Chroma returns a <b>distance</b>, where <b>0.0 means "
  "identical</b>. Displayed raw, a perfect match would show as a score of "
  "zero, and the numbers would read backwards to every user. Converting with "
  "<font face='Courier' size='9'>max(0.0, 1.0 - distance)</font> flips the "
  "scale so that larger is better, and the guard keeps a score from ever "
  "going negative.")

h2("How to read the scores")
note("<b>0.463 is a good score.</b> It looks poor only because we are trained "
     "to read 0 to 1 as a percentage. It is not one.")
p("A question and its answer are phrased differently &mdash; <i>&ldquo;How "
  "does the model avoid recurrence?&rdquo;</i> against <i>&ldquo;The Lantern "
  "model removes the recurrent connection altogether.&rdquo;</i> Same topic, "
  "different grammatical shape. That gap keeps question-to-passage similarity "
  "in roughly the <b>0.3 to 0.6</b> band even for ideal matches. The effect "
  "is known as the <b>asymmetry problem</b>: questions and answers occupy "
  "slightly different neighbourhoods.")
p("So an absolute score means very little. What carries information is the "
  "<i>ranking</i>, and the <i>gap</i>:")
bullets([
    "On-topic question: <b>0.463, 0.460, 0.442</b>",
    "Off-topic question (vitamin D): <b>0.064, 0.052, 0.025</b>",
])
p("Roughly seven times lower. That gap is real signal, and it becomes "
  "important in the next stage.")

h2("Search always returns something")
note("There is <b>no relevance threshold</b>. Ask about vitamin D and the "
     "search will cheerfully hand back the five least-bad passages about "
     "sequence models. Retrieval has no concept of &ldquo;irrelevant&rdquo; "
     "&mdash; it only ranks. Nothing in stage 4 can tell you a question was a "
     "poor fit for the library.")

# ===========================================================================
h1("Stage 5 &nbsp;&middot;&nbsp; Generation")

h2("Building the numbered context")
code('''[1] From "lantern.pdf", page 3:
The Lantern model removes the recurrent connection altogether. Each
position attends over every other position through a learned similarity
function, so the path length between any two positions is constant...

[2] From "lantern.pdf", page 2:
1 Introduction Recurrent networks process a sequence one position at a
time, carrying a hidden state forward...''')

p("The passages are numbered in retrieval order, and that numbering is the "
  "spine of the entire application:")

code("""passage [1] in prompt  ->  source 1 in response
                       ->  note 1 in the margin
                       ->  the superscript numeral you click""")

note("Break that correspondence anywhere along the chain and citations will "
     "point at the wrong passage <i>while still looking perfectly correct</i>. "
     "It is the most silently dangerous thing in the codebase, which is why "
     "the specification calls it out explicitly.")

h2("The prompt is very small")
p("For the example question, the model received <b>5 passages, about 2,300 "
  "characters</b>. That is its entire universe. The paper has nine pages; the "
  "model saw five excerpts. A 70-page paper produces roughly 650 chunks, and "
  "the model would still see five.")
p("This single fact explains nearly everything about the system's behaviour:")
bullets([
    "<b>Why it can be trusted</b> &mdash; it cannot cite what it was never given.",
    "<b>Why &ldquo;summarise this paper&rdquo; fails</b> &mdash; five passages "
    "out of 650 is not a summary.",
    "<b>Why it is inexpensive</b> &mdash; you pay for 2,300 characters, not 70 pages.",
    "<b>Why retrieval quality is everything</b> &mdash; hand it the wrong five "
    "passages and no language model can rescue the answer.",
])

h2("Temperature 0.1")
p("Temperature governs randomness. At 1.0 a model varies its phrasing "
  "creatively; near 0.0 it is close to deterministic. The low setting keeps "
  "it hugging the source wording rather than paraphrasing into something the "
  "passage does not quite support. For research, faithfulness beats flair.")

h2("The rules that carry weight")
p("Of the five instructions in the system prompt, three do the real work:")
bullets([
    "<b>Rule 1</b> &mdash; <i>&ldquo;Never add outside knowledge, even if you "
    "are confident it is correct.&rdquo;</i> The clause after the comma is the "
    "load-bearing part. Without it, a model that happens to know the answer "
    "will helpfully supply it.",
    "<b>Rule 2</b> &mdash; <i>&ldquo;Cite the passage number after every "
    "claim.&rdquo;</i> This is what makes the margin possible at all.",
    "<b>Rule 3</b> &mdash; <i>&ldquo;If the passages do not answer the "
    "question, say so plainly and stop.&rdquo;</i> This is what produces a "
    "refusal instead of an invention.",
])

h2("Two independent safety layers")
table(["Layer", "What it does", "What it cannot do"],
      [["<b>Retrieval</b><br/>(stage 4)", "Supplies relevant facts and ranks them",
        "Detect that a question is off-topic. It always returns something."],
       ["<b>Instruction</b><br/>(stage 5)", "Constrains what may be done with those facts",
        "Find good passages in the first place."]],
      [32 * mm, 61 * mm, 72 * mm])

p("A question about vitamin D passed through retrieval untouched, returning "
  "three passages at scores of 0.064, 0.052 and 0.025. The model answered:")
code("""The passages do not provide any information about the recommended
daily intake of vitamin D.""")
note("The refusal came <b>entirely from the prompt</b>. The model certainly "
     "knows the answer. Remove rule 3 and it would have answered from memory, "
     "with irrelevant citations attached, and it would have looked "
     "authoritative. Retrieval supplies the facts; instruction governs what "
     "may be done with them. <b>Neither layer is sufficient alone.</b>")

h2("An honest limitation, visible in the output")
p("Look closely at the end of the first retrieved passage:")
code("""...learnable in practice. Lantern: Gated Retrieval for Sequences 3""")
p("That trailing text is the page's running footer, welded onto real content. "
  "The minimum-length filter discards chunks that are <i>only</i> a footer, "
  "but it cannot strip a footer attached to a genuine paragraph. So a little "
  "noise is embedded alongside the meaning.")
p("Real papers are full of this &mdash; journal names, DOIs, page numbers, "
  "copyright lines. A Lancet article will carry "
  "<i>&ldquo;www.thelancet.com Vol 406 August 2, 2025&rdquo;</i> in most of "
  "its chunks, slightly diluting every embedding. It is not fatal, and "
  "stripping repeated headers is a known refinement, but it is worth seeing "
  "rather than being told about.")

# ===========================================================================
h1("The three stages, one line each")
bullets([
    "<b>Stage 3</b> turns meaning into geometry, storing the text and its "
    "coordinates side by side.",
    "<b>Stage 4</b> turns the question into the same geometry and takes the "
    "nearest neighbours &mdash; always returning something, never judging "
    "relevance.",
    "<b>Stage 5</b> hands those neighbours to a model under strict "
    "instructions, where the numbering makes every claim traceable back to a "
    "page.",
])
note("Retrieval decides <i>what the model is allowed to know</i>. The prompt "
     "decides <i>what it is allowed to do with it</i>. Understand those two "
     "sentences and you understand retrieval-augmented generation.")


# ===========================================================================
def decorate(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(22 * mm, 15 * mm, w - 22 * mm, 15 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(INK_SOFT)
    canvas.drawString(22 * mm, 10.5 * mm, "Research Copilot — RAG stages 3 to 5")
    canvas.drawRightString(w - 22 * mm, 10.5 * mm, f"{doc.page}")
    canvas.restoreState()


doc = BaseDocTemplate(
    str(OUT), pagesize=A4,
    leftMargin=22 * mm, rightMargin=22 * mm,
    topMargin=20 * mm, bottomMargin=20 * mm,
    title="Retrieval-Augmented Generation: Stages 3 to 5",
    author="Research Copilot",
)
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=decorate)])
doc.build(story)

print(f"wrote {OUT}")
print(f"size : {OUT.stat().st_size / 1024:.0f} KB")
