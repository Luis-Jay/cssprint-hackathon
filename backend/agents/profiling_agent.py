"""
Profiling & Interactive Agent
Extracts structured business information from user conversations
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.state import AgentState
from agents.json_utils import extract_json
from utils.llm_client import get_llm_client


AGENT_NAME = "Business Profiling Agent"


# The facts that change which permits apply. The business name changes
# nothing, so it is optional and never asked for.
REQUIRED_PROFILE_FIELDS = ("business_type", "location")


def missing_profile_fields(profile: dict) -> list:
    return [f for f in REQUIRED_PROFILE_FIELDS if not (profile or {}).get(f)]


def _next_question(profile: dict) -> str:
    """
    Ask for everything still missing in one message.

    Asking one field per turn took three round trips before the user saw
    anything useful. Optional facts that change the roadmap (food, home-based)
    are invited in the same message, never chased separately.
    """
    missing = missing_profile_fields(profile)
    extras = []
    if profile.get("serves_food") is None:
        extras.append("serves food or drinks")
    if profile.get("is_homebased") is None:
        extras.append("runs from home")
    extra = (f" Also mention if it {' or '.join(extras)}, since that changes "
             "your permits." if extras else "")

    if len(missing) == 2:
        return ("What kind of business is it, and which district or barangay in "
                f"Manila will it operate from?{extra}")
    if "business_type" in missing:
        return ("What kind of business is it? (cafe, sari-sari store, online "
                f"selling, salon...){extra}")
    if "location" in missing:
        return f"Which district or barangay in Manila will it operate from?{extra}"

    name = profile.get("business_name")
    what = f"{name}, a {profile['business_type']}" if name else f"A {profile['business_type']}"
    return f"Got it: {what} in {profile['location']}. Building your roadmap now."


PROFILING_SYSTEM_PROMPT = """You are a business profiling assistant for Manila LGU compliance.
Extract structured business information from user messages.

Extract these fields:
- business_name: Name of the business
- business_type: Type (e.g., "cafe", "restaurant", "retail store", "online selling")
- location: Specific location in Manila (district/barangay)
- capital: Initial capital investment in Philippine Pesos (number only)
- employees: Number of employees (number only)
- floor_area: Floor area in square meters (if mentioned)
- serves_food: Boolean, true if serves food/beverages
- has_signage: Boolean, true if has outdoor signage
- is_homebased: Boolean, true if home-based business
- entity_type: "Sole Proprietorship", "Partnership", "Corporation", or "One Person Corporation"
- owner_age: Age of owner (if mentioned)

CRITICAL: Return ONLY valid JSON with the extracted fields. Use null for missing information.
Temperature is 0, so be deterministic and factual."""


def profiling_agent(state: AgentState) -> AgentState:
    """Extract business profile from user messages"""
    print("\nProfiling Agent Running...")
    
    # Get last user message
    if not state["messages"]:
        print("No messages to process")
        return state
    
    last_message = state["messages"][-1]
    user_text = last_message.get("content", "")
    
    if not user_text:
        return state
    
    # Check if we already have a complete profile
    profile = state.get("user_profile", {})
    if profile and not missing_profile_fields(profile):
        print("Profile already complete, skipping")
        return state
    
    print(f"Processing: '{user_text[:100]}...'")
    
    # Call Claude to extract structured data (shared client + connection pool)
    client = get_llm_client()

    try:
        # Create extraction prompt
        prompt = f"""Extract business information from this user message:

"{user_text}"

Return only valid JSON with these fields: business_name, business_type, location, capital, employees, floor_area, serves_food, has_signage, is_homebased, entity_type, owner_age.

Use null for any missing fields. Return ONLY the JSON, no explanation."""
        
        response = client.invoke_model(
            prompt=prompt,
            system_prompt=PROFILING_SYSTEM_PROMPT
        )
        
        content = response.get("content", "")
        
        # Parse JSON
        try:
            extracted_data = extract_json(content)

            # Merge with existing profile
            current_profile = state.get("user_profile", {})
            updated_profile = {**current_profile, **extracted_data}
            
            # Remove null values
            updated_profile = {k: v for k, v in updated_profile.items() if v is not None}
            
            print(f"Extracted: {list(updated_profile.keys())}")

            state["user_profile"] = updated_profile
            state["assistant_reply"] = _next_question(updated_profile)
            state["responding_agent"] = AGENT_NAME

        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")
            print(f"Response was: {content[:200]}")

    except Exception as e:
        print(f"Error: {e}")
        state["error"] = str(e)
    
    return state


if __name__ == "__main__":
    # Test the profiling agent
    test_state = AgentState(
        messages=[
            {
                "role": "user",
                "content": "I want to open a small cafe in Sampaloc. I have around 500,000 pesos capital and plan to hire 3 employees."
            }
        ],
        user_profile={},
        roadmap=[],
        documents=[],
        current_stage="profiling",
        rag_context=None,
        error=None
    )
    
    result = profiling_agent(test_state)
    
    print("\n" + "="*60)
    print("Test Result:")
    print("="*60)
    print(json.dumps(result["user_profile"], indent=2))
