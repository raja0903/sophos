# sophos_ai_backend/core/rag_bot.py

# --- Main Imports ---
import os
import time
import json
import logging
from typing import List, Dict, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import torch
import asyncio
import shutil
import pickle

# --- LangChain and Related Imports ---
from langchain_community.document_loaders import (
    UnstructuredPDFLoader, TextLoader, CSVLoader, UnstructuredWordDocumentLoader, UnstructuredExcelLoader
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import Qdrant
from langchain_ollama import OllamaLLM as Ollama
from langchain.chains import RetrievalQA
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_core.retrievers import BaseRetriever
import qdrant_client
from qdrant_client import QdrantClient
from langchain_core.callbacks import AsyncCallbackManagerForRetrieverRun
from langchain_community.document_loaders.pdf import PyPDFLoader
from langchain_core.documents import Document
from qdrant_client import models as qmodels  # typed models for query_points

# --- Local Imports ---
from .config import config

logger = logging.getLogger(__name__)


# --- Helper Classes ---

class FilteredQdrantRetriever(BaseRetriever):
    """
    A custom LangChain retriever that filters documents by a similarity score threshold.
    This class extends the base retriever to add a post-processing step, ensuring
    that only documents with a relevance score above a certain threshold are
    passed to the next stage of the RAG pipeline.
    """
    vectorstore: Qdrant
    k: int
    score_threshold: float

    def _get_relevant_documents(self, query: str, **kwargs: Any) -> List[Document]:
        """Synchronous method for retrieving and filtering documents."""
        # Perform a similarity search with scores using the underlying Qdrant vectorstore.
        docs_and_scores = self.vectorstore.similarity_search_with_score(query, k=self.k)
        # Filter the results, keeping only documents where the score is >= the threshold.
        return [doc for doc, score in docs_and_scores if score <= self.score_threshold]

    async def _aget_relevant_documents(
        self,
        query: str,
        run_manager: AsyncCallbackManagerForRetrieverRun | None = None,
        **kwargs
        ) -> List[Document]:
        """
        Asynchronous wrapper for the synchronous retrieval method.
        This allows the retriever to be used in an async context without blocking
        the event loop by running the blocking DB call in a separate thread.
        """
        return await asyncio.to_thread(self._get_relevant_documents, query)

class Reranker:
    """
    A class to rerank retrieved documents using a more powerful cross-encoder model.
    While the initial retrieval is fast and based on semantic similarity, the reranker
    provides a more nuanced relevance score by comparing the query and each document
    together, significantly improving the quality of the final context.
    """
    def __init__(self):
        # Load the pre-initialized model and tokenizer from the global config.
        self.tokenizer = config.RERANK_TOKENIZER
        self.model = config.RERANK_MODEL
        
    def rerank(self, query: str, documents: List[Document], top_k: int = 5) -> List[tuple[Document, float]]:
        """
        Reranks a list of documents based on their relevance to a query.
        
        Args:
            query: The user's question.
            documents: The list of documents retrieved from the vector store.
            top_k: The number of top documents to return.
            
        Returns:
            A sorted list of tuples (document, score) for the top_k most relevant documents.
        """
        if not documents: return []
        
        # Create pairs of [query, document] for the cross-encoder model.
        # The '[SEP]' token is a standard way to separate the two texts.
        inputs = [f"{query} [SEP] {doc.page_content}" for doc in documents]
        
        # Tokenize the inputs in a batch. `padding=True` ensures all sequences have
        # the same length, and `truncation=True` cuts off sequences longer than the model's max length.
        tokens = self.tokenizer(
            inputs,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt", # Return PyTorch tensors.
        )
        
        # Perform inference with the model. `torch.no_grad()` disables gradient calculation,
        # which is unnecessary for inference and improves performance.
        with torch.no_grad():
            scores = self.model(**tokens).logits.view(-1)
            
        # Sort the original documents based on the calculated scores in descending order.
        sorted_with_scores = sorted(zip(scores, documents), key=lambda x: -x[0])
        
        # Return the top N documents with their scores as specified by top_k.
        # Convert scores to float for JSON serialization
        return [(doc, float(score.item())) for score, doc in sorted_with_scores[:top_k]]

class DocumentProcessor:
    """
    Handles the loading of various file types and splitting them into processable chunks.
    This class abstracts the logic for handling different document formats (.pdf, .txt, etc.)
    and preparing their content for the embedding process.
    """
    def __init__(self):
        # Initialize the embedding model and text splitter from the global config.
        self.embeddings = HuggingFaceEmbeddings(
            model_name=config.EMBEDDING_MODEL, model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP
        )
        # A mapping of file extensions to their corresponding LangChain loader classes.
        self.loaders = {
            '.pdf': UnstructuredPDFLoader, '.txt': TextLoader, '.csv': CSVLoader,
            '.docx': UnstructuredWordDocumentLoader, '.xlsx': UnstructuredExcelLoader,
        }
        
    def load_document(self, file_path: str) -> List[Document]:
        """
        Loads a single document, automatically handling PDF extraction strategy.
        It employs a fallback mechanism for PDFs to ensure text is extracted even
        from scanned or complex documents.
        """
        try:
            file_ext = Path(file_path).suffix.lower()

            if file_ext == '.pdf':
                # Implements a multi-step fallback strategy for robust PDF parsing.
                documents = []
                total_chars = 0
                
                # 1) Try PyPDFLoader first: It's fast and has no native dependencies.
                try:
                    py_loader = PyPDFLoader(file_path)
                    documents = py_loader.load()
                    total_chars = sum(len(d.page_content or "") for d in documents)
                except Exception as e:
                    logger.warning(f"PyPDFLoader failed for {file_path}: {e}")
                    
                # 2) If little text was extracted, fallback to UnstructuredPDFLoader (fast mode).
                # This mode is better for complex layouts but doesn't perform OCR.
                if total_chars < 2000:
                    try:
                        fast_docs = UnstructuredPDFLoader(file_path, strategy="fast").load()
                        fast_chars = sum(len(d.page_content or "") for d in fast_docs)
                        if fast_chars > total_chars:
                            documents = fast_docs
                            total_chars = fast_chars
                    except Exception as e:
                        logger.warning(f"Unstructured fast fallback failed for {file_path}: {e}")

                # 3) As a last resort for scanned PDFs, use hi_res mode. This requires
                # external dependencies (Poppler, Tesseract) and performs OCR.
                if total_chars < 500:
                    # Check if dependencies are available before trying.
                    has_poppler = shutil.which("pdfinfo") and shutil.which("pdftoppm")
                    if has_poppler:
                        try:
                            hi_docs = UnstructuredPDFLoader(
                                file_path, strategy="hi_res", infer_table_structure=True
                            ).load()    
                            hi_chars = sum(len(d.page_content or "") for d in hi_docs)
                            if hi_chars > total_chars:
                                documents = hi_docs
                        except Exception as e:
                            logger.error(f"Unstructured hi_res failed for {file_path}: {e}", exc_info=True)

                if not documents:
                    raise ValueError("Failed to extract any text from PDF")
            else:
                # For non-PDF files, use the appropriate loader from the dictionary.
                loader_class = self.loaders.get(file_ext)
                if not loader_class:
                    raise ValueError(f"Unsupported file type: {file_ext}")
                loader = loader_class(file_path)
                documents = loader.load()

            # Add common metadata to each document chunk for context.
            for doc in documents:
                doc.metadata.update({
                    'source_file': os.path.basename(file_path),
                    'file_type': file_ext,
                    'processed_at': time.time(),
                })
            return documents

        except Exception as e:
            logger.error(f"Error loading document {file_path}: {e}", exc_info=True)
            return []
        
    def process_documents_batch(self, file_paths: List[str]) -> List[Document]:
        """
        Loads and splits multiple documents in parallel for efficient ingestion.
        """
        all_loaded_docs = []
        # Use a ThreadPoolExecutor to load documents concurrently, speeding up the process.
        with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
            future_to_file = {executor.submit(self.load_document, fp): fp for fp in file_paths}
            for future in future_to_file:
                all_loaded_docs.extend(future.result())
        # After loading, split all documents into smaller chunks using the text splitter.
        return self.text_splitter.split_documents(all_loaded_docs)
    
class HybridQdrantRetriever(BaseRetriever):
    """
    Hybrid dense+sparse retriever:
      - Tries server-side fusion (query_points + Fusion.RRF) via Prefetch
      - Falls back to two-search + local RRF if query_points/fusion is unavailable
    """
    vectorstore: Qdrant
    qdrant_client: QdrantClient
    embeddings: HuggingFaceEmbeddings
    k: int
    tfidf_path: str
    rrf_k: int = getattr(config, "RRF_K", 60)
    topk_each: int = getattr(config, "HYBRID_TOPK_EACH", 50)

    def _sparse_query(self, q: str) -> qmodels.SparseVector:
        with open(self.tfidf_path, "rb") as f:
            vec = pickle.load(f)
        X = vec.transform([q]).tocoo()
        return qmodels.SparseVector(indices=X.col.tolist(), values=X.data.tolist())

    # ---- native (preferred) ----
    def _native_fusion(self, query: str) -> List[Document]:
        dvec = self.embeddings.embed_query(query)
        svec = self._sparse_query(query)
        resp = self.qdrant_client.query_points(
            collection_name=self.vectorstore.collection_name,
            prefetch=[
                qmodels.Prefetch(query=svec, using="sparse", limit=self.topk_each),
                qmodels.Prefetch(query=dvec, using="dense",  limit=self.topk_each),
            ],
            query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
            limit=self.k,
            with_payload=True,
        )
        return [
            Document(page_content=(p.payload or {}).get("text", ""), metadata=p.payload or {})
            for p in resp.points
        ]

    # ---- fallback (legacy) ----
    def _local_rrf(self, dense_hits, sparse_hits):
        def ranks(hits): return {str(p.id): r for r, p in enumerate(hits, 1)}
        rd, rs = ranks(dense_hits), ranks(sparse_hits)
        rep = {str(p.id): p for p in (dense_hits + sparse_hits)}
        out, INF = [], 10**9
        for pid in set(rd) | set(rs):
            s = (1/(self.rrf_k + rd.get(pid, INF))) + (1/(self.rrf_k + rs.get(pid, INF)))
            out.append((rep[pid], s))
        out.sort(key=lambda x: x[1], reverse=True)
        return [p for p, _ in out[:self.k]]

    def _fallback_two_search_rrf(self, query: str) -> List[Document]:
        dvec = self.embeddings.embed_query(query)
        svec = self._sparse_query(query)
        dense_hits = self.qdrant_client.query_points(
            collection_name=self.vectorstore.collection_name,
            query=qmodels.QueryVector(
                vector=qmodels.NamedVector(
                    name="dense",
                    vector=dvec
                )
            ),
            limit=self.topk_each, with_payload=True,
        )
        sparse_hits = self.qdrant_client.query_points(
            collection_name=self.vectorstore.collection_name,
            query=qmodels.QueryVector(
                vector=qmodels.NamedVector(
                    name="sparse",
                    vector=qmodels.SparseVector(
                        indices=svec.indices,
                        values=svec.values
                    )
                )
            ),
            limit=self.topk_each, with_payload=True,
        )
        fused = self._local_rrf(dense_hits, sparse_hits)
        return [
            Document(page_content=(h.payload or {}).get("text", ""), metadata=h.payload or {})
            for h in fused
        ]

    def _get_relevant_documents(self, query: str, **kwargs) -> List[Document]:
        try:
            return self._native_fusion(query)     # single round-trip, server-side fusion
        except Exception:
            return self._fallback_two_search_rrf(query)  # safe fallback    

class QdrantVectorManager:
    """
    Manages all interactions with the Qdrant vector database, including
    adding documents and creating retrievers.
    """
    def __init__(self, embeddings):
        self.embeddings = embeddings
        self.collection_name = "rag_documents"
        # Initialize the Qdrant client using connection details from the config.
        self.qdrant_client = qdrant_client.QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY)
        # Ensure the collection exists before proceeding.
        self.ensure_collection_exists()
        # Create a LangChain Qdrant vectorstore instance for easier interaction.
        self.vectorstore = Qdrant(
            client=self.qdrant_client, collection_name=self.collection_name,
            embeddings=self.embeddings, vector_name="dense"
        )
    def add_documents(self, documents: List[Document]):
        """Adds a batch of documents to the Qdrant collection."""
        self.vectorstore.add_documents(documents)
        
    def get_retriever(self) -> BaseRetriever:
        """Prefer native hybrid if TF-IDF exists; else dense-only with score filter."""
        tfidf = getattr(config, "TFIDF_PATH", "data/tfidf_vectorizer.pkl")
        if os.path.exists(tfidf):
            return HybridQdrantRetriever(
                vectorstore=self.vectorstore,
                qdrant_client=self.qdrant_client,
                embeddings=self.embeddings,
                k=getattr(config, "SEARCH_K", 40),
                tfidf_path=tfidf,
            )
        return FilteredQdrantRetriever(
            vectorstore=self.vectorstore,
            k=getattr(config, "SEARCH_K", 40),
            score_threshold=getattr(config, "SIMILARITY_THRESHOLD", 0.6),
        )
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Retrieves metadata about the Qdrant collection."""
        return self.qdrant_client.get_collection(collection_name=self.collection_name).dict()
    
    def clear_collection(self):
        """Deletes and recreates the collection, effectively clearing all data."""
        self.qdrant_client.delete_collection(collection_name=self.collection_name)
        self.ensure_collection_exists()
        
    def ensure_collection_exists(self):
        """
        Ensure collection exists without overwriting schema that may already include
        named vectors ('dense', 'sparse'). If missing, create with a named 'dense' vector.
        """
        try:
            self.qdrant_client.get_collection(collection_name=self.collection_name)
            return  # exists; do not recreate
        except Exception:
            pass

        dim = len(self.embeddings.embed_query("test"))
        self.qdrant_client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                "dense": qdrant_client.http.models.VectorParams(
                    size=dim, distance=qdrant_client.http.models.Distance.COSINE
                )
            },
        )

# --- Main RAGBot Class ---
class RAGBot:
    """
    The main RAG orchestrator, designed for asynchronous streaming.
    This class ties together document processing, vector management, reranking,
    and LLM interaction to provide a complete, streamable query-answering pipeline.
    """
    def __init__(self):
        # Initialize all the component classes.
        self.doc_processor = DocumentProcessor()
        self.vector_manager = QdrantVectorManager(embeddings=self.doc_processor.embeddings)
        self.reranker = Reranker()
        # The system prompt is a critical instruction that guides the LLM's behavior,
        # ensuring it adheres to the rules of the RAG system.
        self.system_prompt = (
            "You are Sophos AI, an expert in Axway Secure Transport. "
            "Answer the user's question based *strictly* on the provided context. "
            "If the context does not contain the answer, state that you cannot find the information in the provided documents "
            "and suggest contacting Axway Global support. "
            "Be concise and direct.\n\n"
            "IMPORTANT: Show your reasoning process within <think> tags first. "
            "In the thinking section, analyze which sources are relevant and how you'll use them to answer. "
            "Then provide the final answer."
        )

    @staticmethod
    def _format_docs(docs: List[Document]) -> str:
        """A helper method to combine the content of multiple documents into a single string."""
        if not docs:
            return ""
        return "\n\n".join(d.page_content for d in docs)

    def _initialize_qa_chain(self):
        """
        Builds the final question-answering chain using LangChain Expression Language (LCEL).
        This chain takes the question and context and streams the LLM's response.
        """
        # Import necessary LangChain components locally.
        from langchain_community.chat_models import ChatOllama
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser
        import logging

        logger = logging.getLogger(__name__)

        # Initialize the LLM using Ollama provider
        logger.info(f"Using Ollama provider: model={config.OLLAMA_MODEL}, base_url={config.OLLAMA_BASE_URL}")
        llm = ChatOllama(
            model=config.OLLAMA_MODEL,
            base_url=config.OLLAMA_BASE_URL,
            temperature=0.1,  # Low temperature for more deterministic, factual answers.
            streaming=True,  # Critical for enabling token-by-token streaming.
        )

        # Create a prompt template that includes the system prompt and placeholders
        # for the user's question and the retrieved context.
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            ("human", "Context:\n{context}\n\nQuestion: {question}\n\nAnswer:")
        ])

        # Define the streaming chain: prompt -> llm -> output parser.
        # The StrOutputParser converts the LLM's output chunks into strings.
        chain = prompt | llm | StrOutputParser()
        return chain

    async def stream_query(self, question: str):
        """
        The main asynchronous method to handle a user's query from start to finish.
        It retrieves, reranks, and then streams final answer back to the client
        using Server-Sent Events (SSE) format.
        
        Args:
            question: The user's current question
        """
        print(f"\n--- NEW QUERY (astream): {question} ---")
        query_start_time = time.time()

        # Define a synchronous function for retrieval and reranking.
        def sync_retrieve_and_rerank():
            retrieval_start = time.time()
            # Step 1: Retrieve initial documents from the vector store.
            initial_docs = self.vector_manager.get_retriever()._get_relevant_documents(question)
            print(f"DEBUG: Initial documents found: {len(initial_docs)}")
            # Step 2: Rerank the initial documents for better relevance.
            reranked = self.reranker.rerank(question, initial_docs, top_k=config.SEARCH_K)
            print(f"DEBUG: Reranked documents found: {len(reranked)}")
            retrieval_time = time.time() - retrieval_start
            return reranked, retrieval_time

        # Run the blocking sync function in a separate thread to avoid blocking the async event loop.
        reranked_docs, retrieval_time = await asyncio.to_thread(sync_retrieve_and_rerank)

        # Calculate confidence score from reranker scores
        if reranked_docs:
            scores = [score for _, score in reranked_docs]
            confidence_score = float(sum(scores) / len(scores))
        else:
            confidence_score = 0.0

        # Extract documents from tuples
        docs_only = [doc for doc, _ in reranked_docs]

        # Yield the source documents first as a 'sources' event. This allows the UI
        # to display the sources immediately while the LLM is generating the answer.
        source_data = [{
            "page_content": doc.page_content,
            "metadata": doc.metadata
        } for doc in docs_only]
        
        # Include metadata about the retrieval
        sources_metadata = {
            "sources": source_data,
            "confidence_score": round(confidence_score, 4),
            "retrieval_time_ms": round(retrieval_time * 1000, 2),
            "num_sources": len(docs_only)
        }
        
        yield f"event: sources\ndata: {json.dumps(sources_metadata)}\n\n"

        # Prepare the context string from the final, reranked documents.
        context_str = self._format_docs(docs_only)

        # Build the final LLM chain for streaming.
        chain = self._initialize_qa_chain()

        print("DEBUG: Starting chain.astream()...")
        # Asynchronously iterate over the streaming output of the chain.
        async for chunk in chain.astream({"question": question, "context": context_str}):
            # Each `chunk` is a small piece of the generated answer (a token or two).
            # Yield it as a 'token' event in SSE format.
            print(f"DEBUG: Received chunk: '{chunk}'")
            yield f"event: token\ndata: {json.dumps({'token': chunk})}\n\n"

        print("DEBUG: chain.astream() finished.")
        
        # Calculate total query time
        total_time = time.time() - query_start_time
        
        # After the stream is complete, send a final 'end' event with timing info.
        end_data = {
            "total_time_ms": round(total_time * 1000, 2),
            "thought_time_ms": round((total_time - retrieval_time) * 1000, 2)
        }
        yield f"event: end\ndata: {json.dumps(end_data)}\n\n"
        print("--- QUERY FINISHED ---")
