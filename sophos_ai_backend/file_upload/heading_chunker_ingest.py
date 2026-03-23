# -*- coding: utf-8 -*-
"""
Heading-aware PDF chunker (with strong text normalization)

What it does
------------
1) Parse a PDF into paragraphs, normalize text (fix garbled PDF text, de-hyphenate).
2) Detect headings & build a section tree.
3) Chunk using strategy:
   - Procedures / step lists: ~300–500 tokens, 0% overlap (tight actionable units)
   - Concept/explanatory text: ~900–1100 tokens, ~15% overlap (retain context)
   - Tables: one table per chunk
4) Return either raw dict chunks or LangChain Documents.

Extras
------
- Token counting via tiktoken (fallback heuristic if unavailable).
- Optional helpers:
  * embed_dense_e5(model)  -> normalized, mean-pooled embeddings
  * fit_tfidf(texts)       -> sparse vectors + vectorizer
  * upsert_qdrant_rest(...) to send to Qdrant directly (named vectors "dense" and optional "sparse")

Install (minimal)
-----------------
pip install pdfplumber tiktoken

Optional (if you use helpers below):
pip install qdrant-client sentence-transformers scikit-learn requests langchain

CLI (demo)
----------
# Just chunk & print a summary
python heading_chunker_ingest.py --pdf /path/to/file.pdf

# Chunk and upsert via REST to Qdrant (hybrid)
python heading_chunker_ingest.py --pdf /path/to/file.pdf \
  --rest --qdrant-url http://localhost:6333 --collection rag_documents \
  --dense-model intfloat/e5-base-v2 --with-sparse --recreate
"""

from __future__ import annotations
import math
import os
import re
import uuid
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------- Token counting ----------------------

def _try_tiktoken():
    try:
        import tiktoken  # type: ignore
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None

_ENC = _try_tiktoken()

def count_tokens(text: str) -> int:
    """Best-effort token estimate; falls back to 4 chars ~ 1 token."""
    if _ENC:
        try:
            return len(_ENC.encode(text))
        except Exception:
            pass
    return max(1, math.ceil(len(text) / 4))


# ---------------------- PDF → paragraphs ----------------------

@dataclass
class Block:
    text: str
    page: int

# Strong normalizer to fix common PDF extraction artifacts
_WS = re.compile(r"[ \t]+")
_WS_LINES = re.compile(r"[ \t]*\n[ \t]*")
_DEHYPH = re.compile(r"(\w)-\n(\w)")
_MANY_WS = re.compile(r"[ \t]{2,}")

def _undouble_line(line: str) -> str:
    """Collapse AA BB CC artifacts: 'EEnnaabbllee' -> 'Enable' if pattern dominates."""
    if len(line) < 6:
        return line
    doubled = sum(1 for i in range(1, len(line)) if line[i] == line[i - 1])
    if doubled >= len(line) * 0.35:
        out = []
        i = 0
        while i < len(line):
            out.append(line[i])
            if i + 1 < len(line) and line[i + 1] == line[i]:
                i += 2
            else:
                i += 1
        return "".join(out)
    return line

def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    # De-hyphenate line breaks like "trans-\nfer" -> "transfer" before joining
    s = _DEHYPH.sub(r"\1\2", s)
    # Normalize whitespace within and across lines
    s = _WS.sub(" ", s)
    s = _WS_LINES.sub("\n", s)
    # Collapse doubled letters on each line if pattern dominates
    s = "\n".join(_undouble_line(ln) for ln in s.splitlines())
    # Final whitespace cleanup
    s = _MANY_WS.sub(" ", s)
    return s.strip()

def parse_pdf_blocks(pdf_path: str) -> List[Block]:
    import pdfplumber  # type: ignore
    out: List[Block] = []
    with pdfplumber.open(pdf_path) as pdf:
        for pi, page in enumerate(pdf.pages, start=1):
            raw = page.extract_text(layout=True) or ""
            # keep line breaks; strip RHS whitespace to prevent accidental joins
            raw = "\n".join(line.rstrip() for line in raw.splitlines())
            # paragraph buffer with blank-line separation
            buf: List[str] = []

            def flush():
                if not buf:
                    return
                para = "\n".join(buf).strip()
                para = normalize_text(para)
                if para:
                    out.append(Block(para, pi))
                buf.clear()

            for ln in raw.split("\n"):
                if ln.strip() == "":
                    flush()
                else:
                    buf.append(ln)
            flush()
    return out


# ---------------------- Heading detection ----------------------

HEADING_NUM_RE = re.compile(r"^(\d+(?:\.\d+){0,3})\s+(.+?)\s*$")
ALLCAPS_RE = re.compile(r"^[A-Z0-9 \-_/]{3,}$")
TITLE_LIKE_RE = re.compile(r"^([A-Z][^.!?]{2,120})$")
BULLET_RE = re.compile(r"^\s*([•\-\*\u2022\u25E6\u00B7]|\d+[\.\)])\s+")

def is_heading(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > 140:
        return False
    if HEADING_NUM_RE.match(line):
        return True
    if line.endswith("."):
        return False
    if ALLCAPS_RE.match(line):
        return True
    if TITLE_LIKE_RE.match(line):
        return not any(line.endswith(x) for x in ("?", "!"))
    return False

def heading_level(title: str) -> int:
    m = HEADING_NUM_RE.match(title.strip())
    if m:
        return min(3, max(1, m.group(1).count(".") + 1))
    if ALLCAPS_RE.match(title.strip()):
        return 1
    return 2


# ---------------------- Section tree ----------------------

@dataclass
class Section:
    level: int
    title: str
    page_start: int
    page_end: int
    children: List["Section"] = field(default_factory=list)
    blocks: List[Block] = field(default_factory=list)

    @property
    def path(self) -> List[str]:
        return [self.title] if self.level > 0 else []

def build_sections(blocks: List[Block]) -> Section:
    root = Section(level=0, title="ROOT", page_start=1, page_end=1)
    stack = [root]
    for blk in blocks:
        # a block is considered a "pure heading" if it is a single-line and matches is_heading
        lines = blk.text.split("\n")
        if len(lines) == 1 and is_heading(lines[0]):
            lvl = heading_level(lines[0])
            sect = Section(level=lvl, title=lines[0].strip(), page_start=blk.page, page_end=blk.page)
            while stack and stack[-1].level >= lvl:
                stack.pop()
            stack[-1].children.append(sect)
            stack.append(sect)
        else:
            stack[-1].blocks.append(blk)
            stack[-1].page_end = max(stack[-1].page_end, blk.page)
    return root


# ---------------------- Chunking ----------------------

def _split_paragraphs_keep_lists(text: str) -> List[str]:
    out, buf = [], []
    for ln in text.split("\n"):
        if ln.strip() == "":
            if buf:
                out.append("\n".join(buf).strip()); buf = []
        else:
            buf.append(ln)
    if buf:
        out.append("\n".join(buf).strip())
    return out

def _looks_like_procedure(text: str) -> bool:
    lines = text.split("\n")
    bullets = sum(1 for ln in lines if BULLET_RE.match(ln))
    if bullets >= 3:
        return True
    return bool(re.search(r"\b(Procedure|Steps|Step|To (configure|set up|enable|create))\b", text, re.I))

def _looks_like_table(text: str) -> bool:
    # crude grid detection via multi-space/tab column splits over several rows
    rows = [ln for ln in text.split("\n") if ln.strip()]
    gridy = 0
    for ln in rows:
        cols = re.split(r"\s{2,}|\t", ln.strip())
        if len(cols) >= 2:
            gridy += 1
    return gridy >= 3

def chunk_section(
    section: Section,
    ancestors: List[str],
    chunks: List[Dict[str, Any]],
    concept_max_tokens: int = 1000,
    concept_overlap_tokens: int = 150,
    procedure_max_tokens: int = 450,
) -> None:
    path = ancestors + section.path

    # Gather normalized paragraphs for this section
    paras: List[Tuple[str, int, int]] = []
    for blk in section.blocks:
        for p in _split_paragraphs_keep_lists(blk.text):
            # paragraphs already normalized during parsing
            paras.append((p, blk.page, blk.page))

    buf: List[Tuple[str, int, int]] = []
    buf_type: Optional[str] = None

    def flush():
        nonlocal buf, buf_type
        if not buf:
            return
        joined = "\n\n".join(p for p, _, _ in buf)
        s_page = buf[0][1]
        e_page = buf[-1][2]

        if buf_type == "table":
            chunks.append({
                "id": str(uuid.uuid4()),
                "text": joined,
                "section_path": path,
                "page_start": s_page,
                "page_end": e_page,
                "flags": {"is_table": True},
            })

        elif buf_type == "procedure":
            toks = 0
            cur: List[str] = []
            cur_s, cur_e = s_page, e_page
            for p, s, e in buf:
                pt = count_tokens(p)
                if toks + pt > procedure_max_tokens and cur:
                    chunks.append({
                        "id": str(uuid.uuid4()),
                        "text": "\n\n".join(cur),
                        "section_path": path,
                        "page_start": cur_s,
                        "page_end": cur_e,
                        "flags": {"is_procedure": True},
                    })
                    cur, toks = [], 0
                    cur_s, cur_e = s, e
                cur.append(p); toks += pt; cur_e = e
            if cur:
                chunks.append({
                    "id": str(uuid.uuid4()),
                    "text": "\n\n".join(cur),
                    "section_path": path,
                    "page_start": cur_s,
                    "page_end": cur_e,
                    "flags": {"is_procedure": True},
                })

        else:
            # concept window w/ overlap
            tokens: List[str] = []
            spans: List[Tuple[int, int, str, int, int]] = []  # a,b,text,s,e
            for p, s, e in buf:
                ptoks = p.split()
                a, b = len(tokens), len(tokens) + len(ptoks)
                spans.append((a, b, p, s, e))
                tokens.extend(ptoks)
            n = len(tokens)
            start = 0
            max_t, ov = concept_max_tokens, concept_overlap_tokens
            while start < n:
                end = min(n, start + max_t)
                parts: List[str] = []
                ss, ee = s_page, e_page
                for a, b, ptext, s, e in spans:
                    if b <= start or a >= end:
                        continue
                    parts.append(ptext)
                    ss = min(ss, s); ee = max(ee, e)
                if parts:
                    chunks.append({
                        "id": str(uuid.uuid4()),
                        "text": "\n\n".join(parts),
                        "section_path": path,
                        "page_start": ss,
                        "page_end": ee,
                        "flags": {"is_concept": True},
                    })
                if end == n:
                    break
                start = end - ov

        buf, buf_type = [], None

    # classify & accumulate paragraphs
    for p, s, e in paras:
        pt = "table" if _looks_like_table(p) else ("procedure" if _looks_like_procedure(p) else "concept")
        if buf_type is None or pt == buf_type:
            buf.append((p, s, e)); buf_type = pt if buf_type is None else buf_type
        else:
            flush()
            buf_type = pt
            buf.append((p, s, e))
    flush()

    # recurse into children
    for child in section.children:
        chunk_section(child, path, chunks, concept_max_tokens, concept_overlap_tokens, procedure_max_tokens)


# ---------------------- Public API ----------------------

def chunk_pdf(
    pdf_path: str,
    concept_max_tokens: int = 1000,
    concept_overlap_tokens: int = 150,
    procedure_max_tokens: int = 450,
    min_tokens_per_chunk: int = 20,
) -> List[Dict[str, Any]]:
    """Return list of chunk dicts: text + metadata."""
    blocks = parse_pdf_blocks(pdf_path)
    root = build_sections(blocks)
    chunks: List[Dict[str, Any]] = []
    chunk_section(
        root, [], chunks,
        concept_max_tokens=concept_max_tokens,
        concept_overlap_tokens=concept_overlap_tokens,
        procedure_max_tokens=procedure_max_tokens,
    )
    # filter tiny chunks
    out = [c for c in chunks if c["text"].strip() and count_tokens(c["text"]) >= min_tokens_per_chunk]
    return out

def chunk_pdf_to_documents(pdf_path: str, **kwargs) -> List["Document"]:
    """Return LangChain Documents to re-use existing vectorstore ingestion."""
    try:
        from langchain.schema import Document  # type: ignore
    except Exception as e:
        raise RuntimeError("Install langchain to use chunk_pdf_to_documents()") from e

    chunks = chunk_pdf(pdf_path, **kwargs)
    docs: List[Document] = []
    for ch in chunks:
        meta = {
            "source_file": os.path.basename(pdf_path),
            "page_start": ch["page_start"],
            "page_end": ch["page_end"],
            "section_path": ch["section_path"],
            "flags": ch["flags"],
        }
        docs.append(Document(page_content=ch["text"], metadata=meta))
    return docs


# ---------------------- Optional helpers ----------------------

def embed_dense_e5(model_name: str = "intfloat/e5-base-v2"):
    """Return a tiny wrapper with .encode(list[str]) -> List[List[float]] (L2-normalized)."""
    from sentence_transformers import SentenceTransformer  # type: ignore
    m = SentenceTransformer(model_name)
    class _Wrapper:
        def encode(self, texts: List[str]):
            return m.encode(texts, normalize_embeddings=True, show_progress_bar=True).tolist()
    return _Wrapper()

def fit_tfidf(texts: List[str]):
    """Return (indices_list, values_list, fitted_vectorizer)."""
    from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
    v = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_df=0.9, max_features=200_000)
    X = v.fit_transform(texts)
    idxs, vals = [], []
    for i in range(X.shape[0]):
        row = X.getrow(i).tocoo()
        idxs.append(row.col.tolist())
        vals.append(row.data.tolist())
    return idxs, vals, v

def upsert_qdrant_rest(
    url: str,
    collection: str,
    chunks: List[Dict[str, Any]],
    dense_vectors: List[List[float]],
    dense_dim: int,
    sparse_indices: Optional[List[List[int]]] = None,
    sparse_values: Optional[List[List[float]]] = None,
    recreate: bool = False,
    timeout: int = 120,
):
    """Direct REST upsert with named vectors: 'dense' and optional 'sparse'."""
    import requests  # type: ignore

    if recreate:
        requests.delete(f"{url}/collections/{collection}")

    # create/ensure schema
    create_req = {
        "vectors": {"dense": {"size": dense_dim, "distance": "Cosine"}},
    }
    if sparse_indices is not None and sparse_values is not None:
        create_req["sparse_vectors"] = {"sparse": {}}
    requests.put(f"{url}/collections/{collection}", json=create_req, timeout=timeout).raise_for_status()

    # build points
    pts = []
    for i, ch in enumerate(chunks):
        v = {"dense": dense_vectors[i]}
        if sparse_indices is not None and sparse_values is not None:
            v["sparse"] = {"indices": sparse_indices[i], "values": sparse_values[i]}
        pts.append({
            "id": ch.get("id", str(uuid.uuid4())),
            "vector": v,
            "payload": {
                "text": ch["text"],
                "section_path": ch["section_path"],
                "page_start": ch["page_start"],
                "page_end": ch["page_end"],
                "flags": ch["flags"],
            },
        })

    # batch upsert
    B = 256
    for j in range(0, len(pts), B):
        batch = {"points": pts[j:j+B]}
        r = requests.put(f"{url}/collections/{collection}/points?wait=true", json=batch, timeout=timeout)
        r.raise_for_status()


# ---------------------- CLI (demo) ----------------------

if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser(description="Heading-aware chunker")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--concept-max", type=int, default=1000)
    ap.add_argument("--concept-overlap", type=int, default=150)
    ap.add_argument("--procedure-max", type=int, default=450)
    ap.add_argument("--min-chunk-tokens", type=int, default=20)
    # optional REST upsert (hybrid)
    ap.add_argument("--rest", action="store_true")
    ap.add_argument("--qdrant-url", default="http://localhost:6333")
    ap.add_argument("--collection", default="rag_documents")
    ap.add_argument("--dense-model", default="intfloat/e5-base-v2")
    ap.add_argument("--with-sparse", action="store_true")
    ap.add_argument("--recreate", action="store_true")
    args = ap.parse_args()

    chunks = chunk_pdf(
        args.pdf,
        concept_max_tokens=args.concept_max,
        concept_overlap_tokens=args.concept_overlap,
        procedure_max_tokens=args.procedure_max,
        min_tokens_per_chunk=args.min_chunk_tokens,
    )
    print(f"[chunker] chunks: {len(chunks)}")

    if not args.rest:
        # Print a quick summary to stdout and exit
        sample = [
            {
                "id": c["id"],
                "len": len(c["text"]),
                "tok": count_tokens(c["text"]),
                "flags": c["flags"],
                "path": c["section_path"][:3],
                "pages": [c["page_start"], c["page_end"]],
            }
            for c in chunks[:8]
        ]
        print(json.dumps({"sample": sample}, ensure_ascii=False, indent=2))
    else:
        # demo: embed + (optional) tf-idf + upsert
        print("[rest] embedding & upserting to Qdrant…")
        model = embed_dense_e5(args.dense_model)
        dense = model.encode([c["text"] for c in chunks])
        sidx = sval = None
        if args.with_sparse:
            sidx, sval, _ = fit_tfidf([c["text"] for c in chunks])
        upsert_qdrant_rest(
            url=args.qdrant_url,
            collection=args.collection,
            chunks=chunks,
            dense_vectors=dense,
            dense_dim=len(dense[0]),
            sparse_indices=sidx,
            sparse_values=sval,
            recreate=args.recreate,
        )
        print("[rest] done.")

