"""Build small, realistic test PDFs locally so the pipeline can be checked
without downloading anything."""
import sys
from pathlib import Path

# Run from anywhere: put the project root on the import path.
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import sys
import textwrap
from pathlib import Path

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "pdfs"
OUT.mkdir(parents=True, exist_ok=True)


def esc(s):
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def make_pdf(path, pages_lines, with_font=True):
    """pages_lines: list of list-of-strings (one list per page)."""
    objs = {}
    n_pages = len(pages_lines)
    font_num = 3 + 2 * n_pages

    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n_pages))
    objs[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[2] = f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode()

    for i, lines in enumerate(pages_lines):
        page_num = 3 + 2 * i
        content_num = page_num + 1
        if with_font:
            res = f"/Resources << /Font << /F1 {font_num} 0 R >> >>"
        else:
            res = "/Resources << >>"
        objs[page_num] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"{res} /Contents {content_num} 0 R >>"
        ).encode()

        body = ["BT", "/F1 11 Tf", "14 TL", "72 720 Td"]
        for ln in lines:
            body.append(f"({esc(ln)}) Tj")
            body.append("T*")
        body.append("ET")
        stream = "\n".join(body).encode()
        head = f"<< /Length {len(stream)} >>\nstream\n".encode()
        objs[content_num] = head + stream + b"\nendstream"

    if with_font:
        objs[font_num] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman >>"

    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in sorted(objs):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + objs[num] + b"\nendobj\n"

    xref_at = len(out)
    top = max(objs) + 1
    out += f"xref\n0 {top}\n".encode()
    out += b"0000000000 65535 f \n"
    for num in range(1, top):
        out += f"{offsets.get(num, 0):010d} 00000 n \n".encode()
    trailer = f"trailer\n<< /Size {top} /Root 1 0 R >>\nstartxref\n{xref_at}\n"
    out += trailer.encode() + b"%%EOF\n"
    path.write_bytes(bytes(out))
    return path


# A realistic multi-page paper, with hyphenated line breaks on purpose.
PARAS = [
    "Abstract We introduce the Lantern architecture, a sequence model that dispenses with recur~rence"
    " entirely and relies instead on a gated retrieval mechanism. On three benchmark trans~lation"
    " tasks the model matches the accuracy of recurrent baselines while training in less"
    " than a third of the wall-clock time. We attribute the speedup to the absence of sequential"
    " dependencies along the time axis, which allows every position to be computed in parallel.",

    "1 Introduction Recurrent networks process a sequence one position at a time, carrying a"
    " hidden state forward. This sequential structure is the source of both their strength and"
    " their central limitation: the computation for position t cannot begin until position t-1"
    " has finished. Memory constraints then limit batching across examples, and long sequences"
    " become expensive to train.",

    "The Lantern model removes the recurrent connection altogether. Each position attends over"
    " every other position through a learned similarity function, so the path length between any"
    " two positions is constant rather than linear in their distance. Constant path length is"
    " what makes long-range dependencies learnable in practice.",

    "2 Architecture The encoder is a stack of six identical layers. Each layer has two sub~layers:"
    " a multi-head retrieval block and a position-wise feed-forward network. We employ a"
    " residual connection around each sub-layer, followed by layer normalisation. All sub-layers"
    " produce outputs of dimension 512.",

    "2.1 Gated retrieval A retrieval function maps a query and a set of key-value pairs to an"
    " output. The output is a weighted sum of the values, where the weight assigned to each value"
    " is computed by a compatibility function of the query with the corresponding key. We scale"
    " the dot products by the inverse square root of the key dimension, which keeps gradients"
    " well-conditioned as dimension grows.",

    "2.2 Multiple heads Rather than performing a single retrieval with full-dimensional keys, we"
    " project the queries, keys and values h times with different learned projections. Multiple"
    " heads allow the model to attend to information from different representation subspaces at"
    " different positions, which a single averaged head would blur together.",

    "3 Training We trained on the standard corpus of 4.5 million sentence pairs. Sentences were"
    " encoded with a shared vocabulary of 37000 tokens. Each training batch contained approxi~mately"
    " 25000 source tokens and 25000 target tokens. We used the Adam optimiser with a"
    " learning rate that increases linearly for the first 4000 steps and decays thereafter.",

    "4 Results On the English-to-German task the Lantern model reaches 28.4 BLEU, improving over"
    " the best previously reported result by more than 2 BLEU. On English-to-French it reaches"
    " 41.8 BLEU after training for 3.5 days on eight GPUs, a small fraction of the training cost"
    " of the recurrent models it is compared against.",

    "5 Conclusion We presented the Lantern architecture, the first sequence model based entirely"
    " on gated retrieval. The model trains substantially faster than architectures based on"
    " recurrent layers, and it sets a new state of the art on two translation tasks. We are"
    " excited about applying it to inputs other than text.",
]

def wrap_lines(text, width=78):
    """Wrap text, and split a word across the line break at any '~' marker so
    the output contains real end-of-line hyphenation, exactly as a typeset PDF
    does. '~' never survives into the page text."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if "~" in w:
            # Always break here: head keeps a hyphen at the end of this line,
            # tail starts the next one. This is what real typesetting produces.
            head, tail = w.split("~", 1)
            lines.append((cur + " " + head + "-").strip())
            cur = tail
            continue
        candidate = (cur + " " + w).strip()
        if len(candidate) <= width:
            cur = candidate
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


pages = []
for i, para in enumerate(PARAS, start=1):
    lines = wrap_lines(" ".join(para.split()), width=78)
    lines.append("")
    lines.append(f"Lantern: Gated Retrieval for Sequences            {i}")
    pages.append(lines)
make_pdf(OUT / "lantern.pdf", pages)

# A second, shorter paper so the library has more than one document.
OTHER = [
    "Abstract We describe Beacon, a bidirectional encoder pretrained with a masked token"
    " objective. Unlike left-to-right language models, Beacon conditions on context from both"
    " directions at every layer, which produces representations that transfer well to sentence"
    " level tasks.",

    "1 Pretraining objective We mask fifteen percent of the input tokens at random and train the"
    " model to recover them. Because the masked token is never revealed to the encoder, the model"
    " must rely on surrounding context alone. A second objective predicts whether two segments"
    " were adjacent in the source corpus.",

    "2 Fine-tuning For each downstream task we add a single output layer and fine-tune every"
    " parameter end to end. Fine-tuning is inexpensive relative to pretraining: most tasks"
    " converge within three epochs on a single GPU.",
]
pages2 = []
for i, para in enumerate(OTHER, start=1):
    lines = textwrap.wrap(" ".join(para.split()), width=78)
    lines.append("")
    lines.append(f"Beacon: Bidirectional Encoders            {i}")
    pages2.append(lines)
make_pdf(OUT / "beacon.pdf", pages2)

# A "scan": pages with no extractable text at all.
make_pdf(OUT / "scanned.pdf", [[], [], []], with_font=False)

print("wrote:", *(p.name for p in sorted(OUT.glob("*.pdf"))))
