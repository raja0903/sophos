"""
One-off PDF → Qdrant ingest using the SAME embedding model as your chatbot
- Uses Qwen/Qwen3-Embedding-0.6B via HuggingFaceEmbeddings (normalize_embeddings=True).
- Heading-aware chunking (from heading_chunker_ingest.py).
- Dense (required) + optional sparse TF-IDF (hybrid).
- Batch-limited, OOM-resilient embedding loop.
- "Staging" support: save everything after Step 4; later run only Step 5.

USAGE
-----
# A) Full run (chunk → embed → tfidf → create → upsert)
python3.11 one_off_ingest.py \
  --pdf "/path/to/file.pdf" \
  --qdrant-url "http://localhost:6333" \
  --collection "rag_documents" \
  --model "Qwen/Qwen3-Embedding-0.6B" \
  --device cpu \
  --batch-size 8 \
  --with-sparse \
  --recreate \
  --stage-path "data/ingest_stage.pkl" \
  --save-tfidf-path "data/tfidf_vectorizer.pkl"

# B) Save until Step 4 only (no upsert)
python3.11 one_off_ingest.py ... --stage-only

# C) Later, run only Step 5 (reuse staged data)
python3.11 one_off_ingest.py \
  --qdrant-url "http://localhost:6333" \
  --collection "rag_documents" \
  --upsert-only \
  --stage-path "data/ingest_stage.pkl"
"""

from __future__ import annotations
import argparse, os, sys, uuid, pickle
from typing import List, Dict, Any

# --- import the heading-aware chunker ---
try:
    from heading_chunker_ingest import chunk_pdf
except Exception as e:
    print("Error: heading_chunker_ingest.py not found. Place it next to this script.", file=sys.stderr)
    raise

# --- embeddings (same model style as your chatbot) ---
from langchain_community.embeddings import HuggingFaceEmbeddings  # type: ignore

# --- optional sparse features ---
from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore

# --- qdrant client ---
from qdrant_client import QdrantClient  # type: ignore
from qdrant_client.models import (
    Distance,
    VectorParams,
    SparseVectorParams,
    PointStruct,
    SparseVector,
)  # type: ignore


def build_embeddings(model_name: str, device: str = "cpu"):
    """Build HF embeddings; keep device explicit for stability on servers."""
    embed = HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": device},
        encode_kwargs={"normalize_embeddings": True},
    )
    return embed


def fit_tfidf(texts: List[str]):
    v = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_df=0.9, max_features=200_000)
    X = v.fit_transform(texts)
    idxs, vals = [], []
    for i in range(X.shape[0]):
        row = X.getrow(i).tocoo()
        idxs.append(row.col.tolist())
        vals.append(row.data.tolist())
    return idxs, vals, v


def save_stage(stage_path: str, payload: Dict[str, Any]):
    os.makedirs(os.path.dirname(stage_path), exist_ok=True)
    with open(stage_path, "wb") as f:
        pickle.dump(payload, f)


def load_stage(stage_path: str) -> Dict[str, Any]:
    with open(stage_path, "rb") as f:
        return pickle.load(f)


def main():
    ap = argparse.ArgumentParser()
    # Inputs / outputs
    ap.add_argument("--pdf", help="Path to PDF (required unless --upsert-only)")
    ap.add_argument("--stage-path", default="data/ingest_stage.pkl", help="Where to store/load staged data")
    ap.add_argument("--save-tfidf-path", default="data/tfidf_vectorizer.pkl", help="Where to save TF-IDF vectorizer")

    # Qdrant
    ap.add_argument("--qdrant-url", default="http://localhost:6333")
    ap.add_argument("--collection", default="rag_documents")
    ap.add_argument("--recreate", action="store_true", help="Delete & create collection (dangerous)")

    # Embeddings / batching
    ap.add_argument("--model", default="Qwen/Qwen3-Embedding-0.6B")
    ap.add_argument("--device", default="cpu")                 # keep explicit (cpu/cuda/mps)
    ap.add_argument("--batch-size", type=int, default=16)      # batch-limited, OOM-resilient loop

    # Sparse / hybrid
    ap.add_argument("--with-sparse", action="store_true")

    # Modes
    ap.add_argument("--stage-only", action="store_true", help="Run Steps 1-4 and save; skip Step 5")
    ap.add_argument("--upsert-only", action="store_true", help="Load from --stage-path and run Step 5 only")

    args = ap.parse_args()

    # --- Mode: Upsert-only (Step 5) ---
    if args.upsert_only:
        print("[UPSERTER] Loading staged data...")
        stage = load_stage(args.stage_path)
        return run_upsert_only(
            qdrant_url=args.qdrant_url,
            collection=args.collection,
            recreate=args.recreate,
            dense_dim=stage["dense_dim"],
            chunks=stage["chunks"],
            dense_vectors=stage["dense_vectors"],
            sparse_indices=stage.get("sparse_indices"),
            sparse_values=stage.get("sparse_values"),
            created_from_path=stage.get("source_path"),
            with_sparse=("sparse_indices" in stage and "sparse_values" in stage),
        )

    # --- Full or stage-only pipeline (Steps 1-4) ---
    if not args.pdf or not os.path.exists(args.pdf):
        print("Error: --pdf is required (and must exist) unless you pass --upsert-only", file=sys.stderr)
        sys.exit(1)

    # Step 1: Chunk
    print("[1/5] Chunking PDF (heading-aware strategy)...")
    chunks: List[Dict[str, Any]] = chunk_pdf(args.pdf)
    texts = [c["text"] for c in chunks]
    print(f"  chunks: {len(chunks)}")

    # Step 2: Build embeddings
    print("[2/5] Building embeddings (same model as chatbot):", args.model)
    embed = build_embeddings(args.model, device=args.device)

    # Step 3: Embed with batch limiting + auto backoff
    print("[3/5] Embedding chunks (batch-limited)...")
    dense_vectors: List[List[float]] = []
    i = 0
    total = len(texts)
    bs_target = max(1, args.batch_size)
    bs = bs_target
    while i < total:
        this_batch = texts[i : i + bs]
        try:
            vecs = embed.embed_documents(this_batch)
            dense_vectors.extend(vecs)
            i += bs
            if bs < bs_target:
                bs = min(bs_target, bs * 2)  # gentle ramp-up
        except RuntimeError as e:
            em = str(e).lower()
            if ("out of memory" in em) or ("can't allocate memory" in em) or ("cannot allocate memory" in em):
                if bs == 1:
                    print("[embed] OOM even at batch=1; aborting.", file=sys.stderr)
                    raise
                bs = max(1, bs // 2)
                print(f"[embed] OOM detected. Reducing batch size to {bs} and retrying...")
            else:
                raise

    dense_dim = len(dense_vectors[0]) if dense_vectors else 0
    print(f"  dense dim: {dense_dim}")

    # Step 4: Optional TF-IDF & save vectorizer
    sparse_indices = sparse_values = None
    if args.with_sparse:
        print("[4/5] Fitting TF-IDF for optional sparse vectors...")
        sidx, sval, v = fit_tfidf(texts)
        sparse_indices, sparse_values = sidx, sval
        os.makedirs(os.path.dirname(args.save_tfidf_path), exist_ok=True)
        with open(args.save_tfidf_path, "wb") as f:
            pickle.dump(v, f)
        print(f"  saved TF-IDF vectorizer → {args.save_tfidf_path}")
    else:
        print("[4/5] Skipping TF-IDF (dense-only mode).")

    # --- Stage & optionally stop here ---
    stage_blob = {
        "source_path": os.path.abspath(args.pdf),
        "dense_dim": dense_dim,
        "chunks": chunks,
        "dense_vectors": dense_vectors,
        "sparse_indices": sparse_indices,
        "sparse_values": sparse_values,
    }
    save_stage(args.stage_path, stage_blob)
    print(f"[STAGE] Saved steps 1–4 → {args.stage_path}")

    if args.stage_only:
        print("[STAGE-ONLY] Done (skipping Step 5).")
        return

    # Step 5: Upsert
    run_upsert_only(
        qdrant_url=args.qdrant_url,
        collection=args.collection,
        recreate=args.recreate,
        dense_dim=dense_dim,
        chunks=chunks,
        dense_vectors=dense_vectors,
        sparse_indices=sparse_indices,
        sparse_values=sparse_values,
        created_from_path=args.pdf,
        with_sparse=args.with_sparse,
    )


def run_upsert_only(
    qdrant_url: str,
    collection: str,
    recreate: bool,
    dense_dim: int,
    chunks: List[Dict[str, Any]],
    dense_vectors: List[List[float]],
    sparse_indices: List[List[int]] | None,
    sparse_values: List[List[float]] | None,
    created_from_path: str | None = None,
    with_sparse: bool = False,
):
    print("[5/5] Creating/ensuring collection in Qdrant...")
    client = QdrantClient(url=qdrant_url)

    # Use new API: collection_exists + (delete) + create_collection
    exists = client.collection_exists(collection)
    if exists and recreate:
        print("  Deleting existing collection (recreate=True)...")
        client.delete_collection(collection)

    if not client.collection_exists(collection):
        # Note: recent qdrant-client expects dicts for *_config
        client.create_collection(
            collection_name=collection,
            vectors_config={"dense": VectorParams(size=dense_dim, distance=Distance.COSINE)},
            sparse_vectors_config=({"sparse": SparseVectorParams()} if with_sparse else None),
        )
        print("  Collection created.")
    else:
        print("  Collection already exists.")

    print("[5/5] Upserting points...")
    points: List[PointStruct] = []
    for i, ch in enumerate(chunks):
        vec: Dict[str, Any] = {"dense": dense_vectors[i]}
        if with_sparse and sparse_indices and sparse_values:
            vec["sparse"] = SparseVector(indices=sparse_indices[i], values=sparse_values[i])

        payload = {
            "text": ch["text"],
            "section_path": ch["section_path"],
            "page_start": ch["page_start"],
            "page_end": ch["page_end"],
            "flags": ch["flags"],
        }
        if created_from_path:
            payload["source_file"] = os.path.basename(created_from_path)

        points.append(PointStruct(id=ch.get("id", str(uuid.uuid4())), vector=vec, payload=payload))

    # batch upsert
    B = 256
    for i in range(0, len(points), B):
        client.upsert(collection_name=collection, points=points[i : i + B], wait=True)
        print(f"  upserted {min(i + B, len(points))}/{len(points)}")

    print("Done. Collection:", collection)


if __name__ == "__main__":
    main()

