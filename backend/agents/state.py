"""
Agent State Schema for LangGraph
Defines the state structure passed between agents
"""
from typing import TypedDict, List, Dict, Optional
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """
    State passed between agents in the workflow

    This represents all the information collected and processed
    during a user's journey through the PermitPal system.
    """

    # Conversation history
    messages: List[Dict[str, str]]
    
    # User profile (from Profiling Agent)
    user_profile: Dict[str, any]
    
    # Compliance roadmap (from Roadmap Agent)
    roadmap: List[Dict[str, any]]
    
    # Uploaded documents (name/type/size)
    documents: List[Dict[str, any]]

    # Verification verdicts from the Inspection Agent, one per required doc
    verification: List[Dict[str, any]]

    # Set by the upload endpoint to route the next turn to the Inspection Agent
    pending_inspection: bool

    # Which roadmap step the pending upload was filed under, so verification
    # is scoped to that stage instead of every requirement at once
    pending_step: Optional[int]

    # The single upload being verified this turn. `documents` remains the
    # session history and must never be used as evidence for a later upload.
    pending_document: Optional[Dict[str, any]]

    # Natural-language reply for the user, produced by whichever agent ran
    assistant_reply: Optional[str]

    # Which agent produced assistant_reply (shown as the chat byline)
    responding_agent: Optional[str]
    
    # Current stage in the workflow
    current_stage: str
    
    # RAG context (retrieved documents)
    rag_context: Optional[str]
    
    # Retry counters for error handling
    roadmap_retry_count: int

    # How the roadmap was produced: "cache", "rag" or "template"
    roadmap_source: Optional[str]

    # Which stages/sub-steps the user has ticked off
    ui_progress: Dict[str, any]

    # Error handling
    error: Optional[str]


# Default empty state
def get_initial_state() -> AgentState:
    """Get initial empty state"""
    return AgentState(
        messages=[],
        user_profile={},
        roadmap=[],
        documents=[],
        verification=[],
        pending_inspection=False,
        pending_step=None,
        pending_document=None,
        assistant_reply=None,
        responding_agent=None,
        current_stage="profiling",
        rag_context=None,
        roadmap_retry_count=0,
        roadmap_source=None,
        ui_progress={"completed": [], "checked": []},
        error=None
    )
