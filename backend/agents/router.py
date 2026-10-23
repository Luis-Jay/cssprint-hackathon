"""
Router Logic for Conditional Agent Transitions
Determines which agent should run next based on state
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Literal
from agents.state import AgentState


def should_continue_profiling(state: AgentState) -> bool:
    """Check if profiling agent needs to continue gathering info"""
    from agents.profiling_agent import missing_profile_fields

    return bool(missing_profile_fields(state.get("user_profile", {})))


def should_continue_roadmap(state: AgentState) -> bool:
    """Check if roadmap agent needs to generate or update roadmap"""
    roadmap = state.get("roadmap", [])
    
    # If no roadmap exists, need to generate
    if not roadmap or len(roadmap) == 0:
        return True
    
    # If roadmap exists, it's complete
    return False


def route_next_agent(state: AgentState) -> Literal["profiling", "roadmap", "inspection", "end"]:
    """Main router function that determines next agent"""
    current_stage = state.get("current_stage", "profiling")
    
    # Stage-based routing
    if current_stage == "profiling":
        if should_continue_profiling(state):
            return "profiling"
        else:
            return "roadmap"
    
    elif current_stage == "roadmap":
        if should_continue_roadmap(state):
            return "roadmap"
        else:
            return "inspection"
    
    elif current_stage == "inspection":
        # Inspection is terminal state
        return "end"
    
    else:
        # Unknown state, end workflow
        return "end"


def detect_stage_from_message(message: str) -> str:
    """Detect which stage the user is in based on message content"""
    message_lower = message.lower()
    
    # Keywords for document upload/inspection
    doc_keywords = ["upload", "document", "file", "certificate", "clearance", "permit"]
    if any(keyword in message_lower for keyword in doc_keywords):
        return "inspection"
    
    # Keywords for roadmap/requirements
    roadmap_keywords = ["requirement", "step", "process", "how to", "what do i need"]
    if any(keyword in message_lower for keyword in roadmap_keywords):
        return "roadmap"
    
    # Default to profiling for new conversations
    return "profiling"


if __name__ == "__main__":
    # Test routing logic
    print("Testing Router Logic\n")
    
    # Test case 1: Incomplete profile
    state1 = {
        "current_stage": "profiling",
        "user_profile": {"business_name": "Test Cafe"},
        "roadmap": [],
        "documents": []
    }
    print(f"Test 1 - Incomplete profile: {route_next_agent(state1)}")
    
    # Test case 2: Complete profile
    state2 = {
        "current_stage": "profiling",
        "user_profile": {
            "business_name": "Test Cafe",
            "business_type": "cafe",
            "location": "Ermita"
        },
        "roadmap": [],
        "documents": []
    }
    print(f"Test 2 - Complete profile: {route_next_agent(state2)}")
    
    # Test case 3: Roadmap generated
    state3 = {
        "current_stage": "roadmap",
        "user_profile": {"business_name": "Test", "business_type": "cafe", "location": "Manila"},
        "roadmap": [{"step": 1, "title": "DTI Registration"}],
        "documents": []
    }
    print(f"Test 3 - Roadmap exists: {route_next_agent(state3)}")
    
    # Test case 4: Inspection stage
    state4 = {
        "current_stage": "inspection",
        "user_profile": {},
        "roadmap": [],
        "documents": [{"name": "DTI.pdf"}]
    }
    print(f"Test 4 - Inspection stage: {route_next_agent(state4)}")
