from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# --- Authentication ---
class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    username: str
    is_admin: bool
    status: str

# --- Core RAG ---
class SourceDocument(BaseModel):
    page_content: str
    metadata: Dict[str, Any]

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="The user's question to the RAG bot.")

class QueryResponse(BaseModel):
    answer: str
    source_documents: List[SourceDocument]

# --- Feedback ---
class ReportRequest(BaseModel):
    username: str
    question: str
    answer: str

class ReportResponse(BaseModel):
    status: str

# --- Status & Admin ---
class StatusResponse(BaseModel):
    status: str

class AdminStatsResponse(BaseModel):
    document_count: int