# sophos_ai_backend/core/config.py

import os
import multiprocessing as mp
from typing import Optional
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from dotenv import load_dotenv

# Load environment variables from a .env file at the project root.
# This allows for flexible configuration without hardcoding sensitive values.
load_dotenv()

class Config:
    """
    Configuration class for managing all application settings.
    This class centralizes all configurable parameters, from database paths to
    ML model identifiers. Models are also pre-loaded here to ensure they are
    available globally and loaded only once at startup, improving performance.
    """
    # --- File System ---
    # Directory for temporarily storing files uploaded by users for processing.
    UPLOAD_DIR: str = "/tmp/rag_uploads"

    # --- Vector Database Connection ---
    # Qdrant vector DB connection details. Qdrant stores the document embeddings.
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_API_KEY: Optional[str] = os.getenv("QDRANT_API_KEY")

    # --- Machine Learning Models ---
    # Embedding model used to convert text documents into numerical vectors.
    EMBEDDING_MODEL: str = "Qwen/Qwen3-Embedding-0.6B"

    # Ollama Language Model (LLM) connection details. This is the model that generates answers.
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://10.151.58.174:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")

    # LLM Provider selection: "ollama" only
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")

    # --- Models Loaded at Startup ---
    # The reranker model and tokenizer are loaded once when the application starts.
    # This avoids the significant overhead of loading them on every API request.
    print("Loading reranker model...")
    RERANK_TOKENIZER = AutoTokenizer.from_pretrained("BAAI/bge-reranker-v2-m3", use_fast=False)

    # Ensure a padding token exists. A pad token is required for batching inputs of
    # varying lengths. If one isn't defined, we try to use the end-of-sequence token
    # or add a new '[PAD]' token as a last resort.
    if RERANK_TOKENIZER.pad_token is None:
        if RERANK_TOKENIZER.eos_token is not None:
            RERANK_TOKENIZER.pad_token = RERANK_TOKENIZER.eos_token
        else:
            RERANK_TOKENIZER.add_special_tokens({"pad_token": "[PAD]"})

    # Load the reranker model itself. This is a cross-encoder model used to refine
    # search results before they are sent to the LLM.
    RERANK_MODEL = AutoModelForSequenceClassification.from_pretrained(
        "BAAI/bge-reranker-v2-m3",
        num_labels=1  # The model outputs a single score (relevance).
    )

    # If we added a new pad token to the tokenizer, the model's token embedding layer
    # must be resized to accommodate the new token in its vocabulary.
    if RERANK_MODEL.get_input_embeddings().num_embeddings != len(RERANK_TOKENIZER):
        RERANK_MODEL.resize_token_embeddings(len(RERANK_TOKENIZER))

    # Ensure the model's configuration is aware of the pad token's ID.
    RERANK_MODEL.config.pad_token_id = RERANK_TOKENIZER.pad_token_id

    # --- Document Processing ---
    # Parameters for splitting large documents into smaller chunks.
    # CHUNK_SIZE: The maximum number of characters in each chunk.
    # CHUNK_OVERLAP: The number of characters to overlap between adjacent chunks
    # to maintain context.
    CHUNK_SIZE: int = 2000
    CHUNK_OVERLAP: int = 300

    # --- Concurrency ---
    # Thread pool settings for parallel tasks like document loading.
    # It's capped at 8 to prevent overwhelming system resources on machines with many cores.
    MAX_WORKERS: int = min(8, mp.cpu_count())

    # --- RAG Retrieval Parameters ---
    # SEARCH_K: The initial number of documents to retrieve from the vector store.
    # SIMILARITY_THRESHOLD: A score below which retrieved documents are considered irrelevant and discarded.
    SEARCH_K: int = 5
    SIMILARITY_THRESHOLD: float = 0.6
    DB_PATH_PREFIX = "data/"
    TFIDF_PATH: str = f"{DB_PATH_PREFIX}tfidf_vectorizer.pkl"
    
    # Native fusion knobs (server-side RRF/DBSF)
    HYBRID_TOPK_EACH: int = 50   # prefetch breadth per modality
    RRF_K: int = 60              # RRF constant

    # --- SQLite Database Paths ---
    # Using a subdirectory for data files is good practice, especially for compiled executables.
    DB_PATH_PREFIX = "data/"
    LOG_CODES_DB: str = f"{DB_PATH_PREFIX}log_codes.db"
    APP_METADATA_DB: str = f"{DB_PATH_PREFIX}app_metadata.db"
    DIAG_CODES_DB: str = f"{DB_PATH_PREFIX}diag_codes.db"
    USER_DB: str = f"{DB_PATH_PREFIX}users.db"

    # --- Notifications ---
    # Microsoft Teams Webhook URL for sending notifications when a user reports an incorrect answer.
    TEAMS_WEBHOOK_URL: str = os.getenv("TEAMS_WEBHOOK_URL", "")

# Instantiate the configuration class to create a single, globally accessible 'config' object.
# Other modules can simply `from .config import config` to access these settings.
config = Config()

# --- Post-config Initialization ---
# Ensure the necessary directories for uploads and databases exist on startup.
# `exist_ok=True` prevents an error if the directories already exist.
os.makedirs(config.UPLOAD_DIR, exist_ok=True)
os.makedirs(config.DB_PATH_PREFIX, exist_ok=True)