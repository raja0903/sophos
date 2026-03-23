# test_qdrant.py — native hybrid fusion with query_points (Qdrant 1.15)
from qdrant_client import QdrantClient, models
from langchain_huggingface import HuggingFaceEmbeddings
import pickle

QDRANT_URL = "http://localhost:6333"
COLL = "rag_documents"
TFIDF_PATH = "/opt/Sophos_AI/sophos_ai_backend/data/tfidf_vectorizer.pkl"

QUERY = "enable FIPS mode and configure allowed TLS ciphers"
TOPK_EACH = 50  # prefetch breadth for dense & sparse
TOPK_FINAL = 10

def main():
    # Dense query vector (same model you used for ingest)
    emb = HuggingFaceEmbeddings(
        model_name="Qwen/Qwen3-Embedding-0.6B",
        encode_kwargs={"normalize_embeddings": True},
    )
    dvec = emb.embed_query(QUERY)

    # Sparse query vector (TF-IDF)
    with open(TFIDF_PATH, "rb") as f:
        vec = pickle.load(f)
    X = vec.transform([QUERY]).tocoo()
    svec = models.SparseVector(indices=X.col.tolist(), values=X.data.tolist())

    client = QdrantClient(url=QDRANT_URL)

    # Native hybrid: prefetch both queries, then fuse with RRF server-side
    resp = client.query_points(
        collection_name=COLL,
        prefetch=[
            models.Prefetch(query=svec, using="sparse", limit=TOPK_EACH),
            models.Prefetch(query=dvec, using="dense",  limit=TOPK_EACH),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=TOPK_FINAL,
        with_payload=True,
    )

    print("\nQuery:", QUERY, "\n")
    for p in resp.points:
        payload = p.payload or {}
        path = " > ".join(payload.get("section_path", []))
        pages = f"[p{payload.get('page_start')}-{payload.get('page_end')}]"
        print(f"{p.score:.5f}  {path}  {pages}")

if __name__ == "__main__":
    main()

