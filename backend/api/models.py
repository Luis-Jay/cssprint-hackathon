"""
Pydantic Models for API Request/Response
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    session_id: str = Field(..., description="Session identifier")
    message: str = Field(..., description="User message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user-123",
                "message": "I want to open a cafe in Manila"
            }
        }


class ChatResponse(BaseModel):
    """Response model for chat endpoint"""
    session_id: str
    response: str
    stage: str
    agent: Optional[str] = Field(
        None, description="Which agent produced the reply (chat byline)"
    )
    profile: Optional[Dict[str, Any]] = None
    roadmap: Optional[List[Dict[str, Any]]] = None
    documents: Optional[List[Dict[str, Any]]] = None
    verification: Optional[List[Dict[str, Any]]] = Field(
        None, description="Per-document verdicts from the Inspection Agent"
    )
    trace: Optional[Dict[str, Any]] = Field(
        None,
        description="Low-level execution trace: routing, retrieval, prompts, "
                    "raw model output, fallbacks and timings for this turn",
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user-123",
                "response": "Got it! Can you tell me more about your business location?",
                "stage": "profiling",
                "profile": {"business_name": "My Cafe"},
                "roadmap": None,
                "documents": None
            }
        }


class DocumentUploadRequest(BaseModel):
    """Request model for document upload"""
    session_id: str
    document_name: str
    document_type: str
    content: Optional[str] = None


class DocumentUploadResponse(BaseModel):
    """Response model for document upload"""
    session_id: str
    status: str
    message: str
    verification_results: Optional[Dict[str, Any]] = None
    agent: Optional[str] = Field(None, description="Which agent produced the findings")
    trace: Optional[Dict[str, Any]] = Field(
        None,
        description="Execution trace for the upload, so the chat can show the "
                    "same agent activity it shows for a chat turn",
    )


class RoadmapCreateRequest(BaseModel):
    """Request model for roadmap creation"""
    session_id: str = Field(..., description="Session identifier")
    profile: Optional[Dict[str, Any]] = Field(
        None,
        description="Business profile. Omit to use the profile already on the session.",
    )


class RoadmapResponse(BaseModel):
    """Response model for roadmap retrieval"""
    session_id: str
    roadmap: List[Dict[str, Any]]
    profile: Dict[str, Any]
    stage: str
    source: Optional[str] = Field(
        None,
        description='How the roadmap was produced: "cache", "rag" or "template"',
    )
    refining: bool = Field(
        False,
        description="True while a RAG-grounded roadmap is still generating in the background",
    )


class SessionResponse(BaseModel):
    """Response model for session state"""
    session_id: str
    stage: str
    profile: Dict[str, Any]
    roadmap: List[Dict[str, Any]]
    documents: List[Dict[str, Any]]
    message_count: int
    messages: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Chat transcript. Only message_count was exposed before, so "
                    "the client had no way to redraw the conversation after a "
                    "re-login even though the server had kept it.",
    )
    progress: Dict[str, Any] = Field(
        default_factory=dict,
        description="Completed stage ids and ticked sub-step ids",
    )
    source: Optional[str] = Field(None, description="How the roadmap was produced")


class ProgressRequest(BaseModel):
    """Request model for saving roadmap progress"""
    completed: List[str] = Field(default_factory=list)
    checked: List[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Response model for health check"""
    status: str
    version: str
    services: Dict[str, str]


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    detail: Optional[str] = None
    session_id: Optional[str] = None


class SignupRequest(BaseModel):
    """Request model for account creation"""
    email: str = Field(..., description="Email address, used to sign in")
    password: str = Field(..., min_length=8, description="At least 8 characters")
    name: Optional[str] = Field(None, description="Display name; defaults to the email local part")

    class Config:
        json_schema_extra = {
            "example": {"email": "juan@example.com", "password": "correct-horse-battery",
                        "name": "Juan Dela Cruz"}
        }


class LoginRequest(BaseModel):
    """Request model for sign in"""
    email: str
    password: str


class UserResponse(BaseModel):
    """Public view of an account - never includes the password hash"""
    id: int
    email: str
    name: str


class AuthResponse(BaseModel):
    """Response model for signup, login and /me"""
    token: str = Field(..., description="Bearer token for the Authorization header")
    user: UserResponse
    session_id: Optional[str] = Field(
        None, description="The agent session this user last worked in, if any"
    )


class WorkspaceRequest(BaseModel):
    """Request model for attaching an agent session to an account"""
    session_id: str
