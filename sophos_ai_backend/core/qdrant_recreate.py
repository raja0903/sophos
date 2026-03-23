from qdrant_client.models import Distance, VectorParams

from qdrant_client import QdrantClient

client = QdrantClient(
    url="http://localhost:6333",   # or your Qdrant Cloud endpoint
)

info = client.get_collection("rag_documents")
print(info)

# Access vector size
print("Vector size:", info.config.params.vectors.size)