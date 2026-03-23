import sys
import os
import json
from typing import List
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# Add project root to path to allow imports from core
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.rag_bot import RAGBot
from core.database import authenticate_user, initialize_all_databases, User
from core.notifications import report_incorrect_answer_to_teams
from core.config import config
from api.schemas import (
    QueryRequest, QueryResponse, LoginRequest, LoginResponse, SourceDocument,
    ReportRequest, ReportResponse, StatusResponse, AdminStatsResponse
)

# --- Initialize Databases and Load the RAG Bot ONCE at startup ---
initialize_all_databases()
rag_bot = RAGBot()

# --- Create FastAPI app ---
app = FastAPI(
    title="Sophos AI",
    description="API for the Axway Secure Transport Expert Bot",
    version="1.0.0"
)

# Add the CORS middleware to your application.
# This must be placed before you define your routes.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (for development)
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

# --- API Endpoints ---

@app.get("/", response_model=StatusResponse, tags=["Status"])
async def read_root():
    """Provides the current status of the API."""
    return {"status": "Sophos AI Backend is running"}

@app.post("/login", response_model=LoginResponse, tags=["Authentication"])
async def login(request: LoginRequest):
    """Handles user authentication."""
    user = authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return LoginResponse(username=user.username, is_admin=user.is_admin, status="Login successful")

@app.get("/query", tags=["RAG"])
async def handle_query_stream(
    question: str = Query(..., min_length=1)
):
    """
    Handles user questions via GET and streams the response using Server-Sent Events.
    
    Args:
        question: The user's question
    """
    try:
        return StreamingResponse(
            rag_bot.stream_query(question),
            media_type="text/event-stream"
        )
    except Exception as e:
        print(f"Error during streaming query: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred during streaming.")

@app.post("/report-incorrect", response_model=ReportResponse, tags=["Feedback"])
async def report_incorrect(request: ReportRequest):
    """Allows users to report an incorrect answer."""
    success = report_incorrect_answer_to_teams(
        username=request.username,
        question=request.question,
        answer=request.answer
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send report to Teams.")
    return ReportResponse(status="Report sent successfully.")

# --- Admin Endpoints ---

@app.post("/admin/upload", tags=["Admin"])
async def upload_documents(files: List[UploadFile] = File(...)):
    """Admin endpoint to upload and process new knowledge documents."""
    # This is a placeholder for user authentication logic.
    # In a real app, you would verify the user is an admin from a token.
    file_paths = []
    try:
        for uploaded_file in files:
            temp_file_path = os.path.join(config.UPLOAD_DIR, uploaded_file.filename)
            with open(temp_file_path, "wb") as f:
                f.write(uploaded_file.file.read())
            file_paths.append(temp_file_path)

        documents = rag_bot.doc_processor.process_documents_batch(file_paths)
        if documents:
            rag_bot.vector_manager.add_documents(documents)
            return {"message": f"Successfully processed {len(files)} files and added {len(documents)} chunks."}
        else:
            return {"message": "No processable content found in the uploaded files."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing documents: {e}")
    finally:
        # Clean up temporary files
        for file_path in file_paths:
            if os.path.exists(file_path):
                os.remove(file_path)


@app.post("/admin/clear-database", tags=["Admin"])
async def clear_database():
    """Admin endpoint to clear the entire Qdrant vector database."""
    try:
        rag_bot.vector_manager.clear_collection()
        return {"message": "Vector database cleared successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing database: {e}")

@app.get("/admin/stats", response_model=AdminStatsResponse, tags=["Admin"])
async def get_stats():
    """Admin endpoint to get statistics about the vector database."""
    try:
        info = rag_bot.vector_manager.get_collection_info()
        doc_count = info.get("points_count", 0) if info and "points_count" in info else 0
        return AdminStatsResponse(document_count=doc_count)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not retrieve stats: {e}")