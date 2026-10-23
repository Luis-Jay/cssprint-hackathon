"""" LangGraph Workflow Orchestration Defines the multi-agent workflow with conditional routing"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agents.state import AgentState, get_initial_state
from agents.profiling_agent import missing_profile_fields, profiling_agent
from agents.roadmap_agent import roadmap_agent
from agents.inspection_agent import inspection_agent
from agents.qa_agent import qa_agent
import observability as obs

logger = logging.getLogger(__name__)


def profile_is_complete(profile: dict) -> bool:
    """A profile is usable once we know the type of business and where it is."""
    return bool(profile) and not missing_profile_fields(profile)


def route_turn(state: AgentState) -> Literal["profiling", "roadmap", "qa", "inspection"]:
    """
    Pick the single agent that should handle this turn.

    Runs as the conditional ENTRY point, so it sees the state as it actually
    is rather than as update_stage has just rewritten it.
    """
    profile = state.get("user_profile") or {}

    def decide(target: str, why: str) -> str:
        logger.info("Route: %s (%s)", target, why)
        obs.emit("route", f"Routing to {target}", agent="router", reason=why,
                 profile_complete=profile_is_complete(profile),
                 has_roadmap=bool(state.get("roadmap")),
                 documents=len(state.get("documents") or []),
                 pending_inspection=bool(state.get("pending_inspection")))
        return target

    # An upload happened; verify it before anything else.
    if state.get("pending_inspection"):
        return decide("inspection", "documents pending verification")

    # Still gathering the basics.
    if not profile_is_complete(profile):
        missing = missing_profile_fields(profile)
        return decide("profiling", f"profile missing {', '.join(missing)}")

    # Profiled but no roadmap yet - build one.
    if not state.get("roadmap"):
        return decide("roadmap", "no roadmap yet")

    # Everything in place: answer the question.
    return decide("qa", "profile and roadmap ready")


def update_stage(state: AgentState) -> AgentState:
    """
    Derive current_stage from what the state now contains.

    Runs once on the way out, after the agent has done its work, so the stage
    reflects reality rather than driving it.
    """
    profile = state.get("user_profile") or {}
    roadmap = state.get("roadmap") or []
    verification = state.get("verification") or []

    if verification:
        stage = "inspection"
    elif roadmap:
        stage = "inspection" if state.get("documents") else "roadmap"
    elif profile_is_complete(profile):
        stage = "roadmap"
    else:
        stage = "profiling"

    if stage != state.get("current_stage"):
        logger.info("Stage: %s -> %s", state.get("current_stage"), stage)
        obs.emit("agent", f"Stage {state.get('current_stage')} -> {stage}",
                 agent="update_stage", previous=state.get("current_stage"), stage=stage)
        state["current_stage"] = stage

    # Consume the one-shot inspection flags so the next turn routes normally.
    state["pending_inspection"] = False
    state["pending_step"] = None
    state["pending_document"] = None

    return state


def build_workflow() -> StateGraph:
    """
    Build the LangGraph workflow with conditional routing

    Returns:
        Compiled StateGraph with checkpointing
    """
    logger.info("Building LangGraph workflow...")

    workflow = StateGraph(AgentState)

    workflow.add_node("profiling", profiling_agent)
    workflow.add_node("roadmap", roadmap_agent)
    workflow.add_node("inspection", inspection_agent)
    workflow.add_node("qa", qa_agent)
    workflow.add_node("update_stage", update_stage)

    # Route on the way in, so the router sees the real stage.
    workflow.set_conditional_entry_point(
        route_turn,
        {
            "profiling": "profiling",
            "roadmap": "roadmap",
            "inspection": "inspection",
            "qa": "qa",
        },
    )

    # Every agent settles the stage and ends. No cycles.
    for node in ("profiling", "roadmap", "inspection", "qa"):
        workflow.add_edge(node, "update_stage")
    workflow.add_edge("update_stage", END)

    logger.info("Workflow graph built successfully")

    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)


# Create the compiled app
app = build_workflow()


def run_workflow(user_message: str, session_id: str = "default") -> AgentState:
    """Run the workflow with a user message"""
    initial_state = get_initial_state()
    initial_state["messages"].append({"role": "user", "content": user_message})

    config = {"configurable": {"thread_id": session_id}}
    return app.invoke(initial_state, config)


def stream_workflow(user_message: str, session_id: str = "default"):
    """Stream the workflow execution step-by-step"""
    initial_state = get_initial_state()
    initial_state["messages"].append({"role": "user", "content": user_message})

    config = {"configurable": {"thread_id": session_id}}
    for event in app.stream(initial_state, config):
        yield event


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    print("\nTesting LangGraph Workflow\n")

    test_message = """I want to open a cafe called 'Test Coffee' in Ermita.
    Capital is 500,000 pesos. We'll have 3 employees and serve food."""

    result = run_workflow(test_message, session_id="test-001")

    print("\nFinal State:")
    print(f"Stage: {result.get('current_stage')}")
    print(f"Profile: {result.get('user_profile', {}).get('business_name', 'N/A')}")
    print(f"Roadmap steps: {len(result.get('roadmap', []))}")
    print(f"Reply: {result.get('assistant_reply')}")
