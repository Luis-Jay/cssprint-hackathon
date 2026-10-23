"""
LGU & Roadmap Knowledge Agent
Generates compliance roadmap using RAG-powered context
"""
import hashlib
import json
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.state import AgentState
from agents.json_utils import extract_json
from utils.llm_client import get_llm_client, get_settings
from rag.retriever import get_retriever

logger = logging.getLogger(__name__)

# Prompt budget for retrieved context
MAX_RAG_CONTEXT_CHARS = 4000

# JSON parse retries. Network/auth failures are not retried - they are not
# recoverable and each attempt costs a full 60s httpx timeout.
MAX_LLM_ATTEMPTS = 2


def get_fallback_roadmap(profile: dict) -> list:
    """Fallback roadmap when API fails"""
    business_type = profile.get("business_type", "business")
    serves_food = profile.get("serves_food", False)

    roadmap = [
        {
            "step_number": 1,
            "title": "DTI Business Name Registration",
            "description": "Register your business name with the Department of Trade and Industry",
            "requirements": ["Valid government ID", "Proposed business names (3 options)"],
            "estimated_time": "1-3 business days",
            "estimated_cost": "₱515",
            "location": "DTI Office or online at bnrs.dti.gov.ph",
            "notes": "Required for sole proprietorship and partnerships"
        },
        {
            "step_number": 2,
            "title": "Barangay Business Clearance",
            "description": "Obtain clearance from your barangay",
            "requirements": ["DTI Certificate", "Valid ID", "Community Tax Certificate"],
            "estimated_time": "1-2 days",
            "estimated_cost": "₱500-1,000",
            "location": f"Barangay Hall in {profile.get('location', 'your location')}",
            "notes": "Fee varies by barangay"
        },
        {
            "step_number": 3,
            "title": "Fire Safety Inspection Certificate",
            "description": "Get fire safety clearance from Bureau of Fire Protection",
            "requirements": ["Location plan", "Fire safety measures documentation", "Building permit"],
            "estimated_time": "3-5 days",
            "estimated_cost": "₱1,000-3,000",
            "location": "BFP Manila District Office",
            "notes": "Required for all commercial establishments"
        },
    ]

    # Add food-specific permits if applicable
    if serves_food:
        roadmap.append({
            "step_number": 4,
            "title": "Sanitary Permit / Health Certificate",
            "description": "Obtain sanitary permit from Manila Health Department",
            "requirements": ["Medical certificates for food handlers", "Stool exam results", "Location sketch"],
            "estimated_time": "5-7 days",
            "estimated_cost": "₱2,000-5,000",
            "location": "Manila Health Department",
            "notes": "Required for food service establishments"
        })

    roadmap.extend([
        {
            "step_number": len(roadmap) + 1,
            "title": "Mayor's Permit / Business Permit",
            "description": "Apply for Manila Mayor's Permit through BPLO",
            "requirements": ["DTI Certificate", "Barangay Clearance", "Fire Safety Certificate", "All line bureau permits", "Lease contract or property title"],
            "estimated_time": "7-10 business days",
            "estimated_cost": "₱5,000-15,000 (depends on gross sales)",
            "location": "Business Permits and Licensing Office (BPLO), Manila City Hall",
            "notes": "Main business permit - renew annually"
        },
        {
            "step_number": len(roadmap) + 2,
            "title": "BIR Registration",
            "description": "Register with Bureau of Internal Revenue for tax purposes",
            "requirements": ["Mayor's Permit", "DTI Certificate", "Lease contract", "Valid IDs"],
            "estimated_time": "3-5 days",
            "estimated_cost": "₱500 (registration fee)",
            "location": "BIR Revenue District Office covering your location",
            "notes": "Get BIR Form 2303 (Certificate of Registration) and official receipts/invoices"
        }
    ])

    return roadmap


ROADMAP_SYSTEM_PROMPT = """You are a Manila LGU compliance expert.
Generate a step-by-step compliance roadmap for businesses based on their profile and Manila ordinances.

The roadmap should include:
1. DTI Registration
2. Barangay Clearance
3. Line Bureau Permits (Fire Safety, Health, etc.)
4. Mayor's Permit (BPLS)
5. BIR Registration

For each step, specify:
- step_number: Sequential number
- title: Step name
- description: What needs to be done
- requirements: List of required documents
- estimated_time: Processing time estimate
- estimated_cost: Fee estimate in Philippine Pesos
- location: Where to apply
- notes: Special considerations

Use the provided RAG context from Manila ordinances as your source of truth.
Temperature is 0, so be factual and cite specific ordinances when applicable."""


# --------------------------------------------------------------------------- Roadmap cache

_CACHE_FIELDS = (
    "business_type",
    "location",
    "serves_food",
    "is_homebased",
    "has_signage",
    "entity_type",
)

_roadmap_cache: Dict[str, Tuple[float, List[dict]]] = {}
_roadmap_cache_lock = threading.Lock()


def _cache_key(profile: dict) -> str:
    """Stable hash over only the fields that change the required permits."""
    payload = json.dumps(
        {k: profile.get(k) for k in _CACHE_FIELDS},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_get(profile: dict) -> Optional[List[dict]]:
    settings = get_settings()
    if not settings.enable_cache:
        return None

    key = _cache_key(profile)
    with _roadmap_cache_lock:
        entry = _roadmap_cache.get(key)

    if entry is None:
        return None

    stored_at, roadmap = entry
    if time.monotonic() - stored_at > settings.cache_ttl_seconds:
        with _roadmap_cache_lock:
            _roadmap_cache.pop(key, None)
        return None

    return roadmap


def _cache_put(profile: dict, roadmap: List[dict]) -> None:
    if not get_settings().enable_cache:
        return
    with _roadmap_cache_lock:
        _roadmap_cache[_cache_key(profile)] = (time.monotonic(), roadmap)


def cached_roadmap(profile: dict) -> Optional[List[dict]]:
    """
    A previously generated RAG roadmap for an equivalent profile, if one exists.

    Lets the API hand out a grounded roadmap immediately instead of promising
    to swap one in later - the roadmap a user is given must never change.
    """
    return _cache_get(profile)


def warm_roadmap_cache(profile: dict) -> None:
    """
    Generate a roadmap purely to populate the cache.

    Deliberately returns nothing and touches no session: this exists so the
    NEXT business with a similar profile gets the grounded roadmap instantly,
    not to retro-fit one onto a session already in use.
    """
    try:
        _, source = generate_roadmap(profile)
        logger.info("Roadmap cache warmed (source=%s)", source)
    except Exception:
        logger.exception("Roadmap cache warm failed")


def clear_roadmap_cache() -> None:
    """Drop every cached roadmap (used by tests and admin tooling)."""
    with _roadmap_cache_lock:
        _roadmap_cache.clear()


def _build_rag_query(profile: dict) -> str:
    """Build the retrieval query from the business profile."""
    business_type = profile.get("business_type", "business")
    location = profile.get("location", "Manila")
    serves_food = profile.get("serves_food", False)

    return f"""Requirements for {business_type} in {location} Manila.
Business permit process, DTI registration, barangay clearance, mayor's permit, BIR requirements.
{"Include food service permits and health department requirements." if serves_food else ""}
Document checklist and fees."""


def _build_prompt(profile: dict, rag_context: str, strict: bool = False) -> str:
    """Build the generation prompt. `strict` hardens the JSON instruction."""
    profile_str = json.dumps(profile, indent=2)

    strict_note = (
        "\n\nIMPORTANT: your previous response could not be parsed as JSON. "
        "Return ONLY the raw JSON array. No markdown fences, no commentary."
        if strict else ""
    )

    return f"""Generate a compliance roadmap for this Manila business:

BUSINESS PROFILE:
{profile_str}

MANILA ORDINANCES & REQUIREMENTS (RAG Context):
{rag_context}

Generate a step-by-step roadmap with 5-8 stages covering:
1. DTI Registration
2. Barangay Clearance
3. Line Bureau Permits (based on business type)
4. Mayor's Permit (BPLS)
5. BIR Registration

Return ONLY valid JSON array format:
[
  {{
    "step_number": 1,
    "title": "DTI Business Name Registration",
    "description": "...",
    "requirements": ["Valid ID", "..."],
    "estimated_time": "1-3 business days",
    "estimated_cost": "₱515",
    "location": "DTI Office or online",
    "notes": "..."
  }},
  ...
]{strict_note}"""


def generate_roadmap(profile: dict) -> Tuple[List[dict], str]:
    """Generate a compliance roadmap for a business profile."""
    cached = _cache_get(profile)
    if cached is not None:
        logger.info("Roadmap cache hit for %s", profile.get("business_name", "unknown"))
        return cached, "cache"

    logger.info(
        "Generating roadmap for %s (%s)",
        profile.get("business_name", "Unknown"),
        profile.get("business_type", "Unknown"),
    )

    # Retrieval. A missing or corrupt vector store is not recoverable, so do
    # not burn LLM calls on it - go straight to the template.
    try:
        retriever = get_retriever()
        rag_context = retriever.retrieve_context(
            _build_rag_query(profile),
            top_k=5,
            max_chars=MAX_RAG_CONTEXT_CHARS,
        )
        logger.info("Retrieved %d chars of RAG context", len(rag_context))
    except Exception:
        logger.exception("RAG retrieval failed; using template roadmap")
        return get_fallback_roadmap(profile), "template"

    client = get_llm_client()

    for attempt in range(1, MAX_LLM_ATTEMPTS + 1):
        try:
            response = client.invoke_model(
                prompt=_build_prompt(profile, rag_context, strict=attempt > 1),
                system_prompt=ROADMAP_SYSTEM_PROMPT,
                max_tokens=4096,
            )
        except Exception:
            # Network / auth / quota. Retrying costs another 60s timeout and
            # will fail the same way, so stop here.
            logger.exception("Model call failed; using template roadmap")
            return get_fallback_roadmap(profile), "template"

        try:
            roadmap = extract_json(response.get("content", ""))
        except json.JSONDecodeError as e:
            logger.warning(
                "Roadmap JSON parse failed (attempt %d/%d): %s",
                attempt, MAX_LLM_ATTEMPTS, e,
            )
            continue

        if not isinstance(roadmap, list) or not roadmap:
            logger.warning(
                "Roadmap was not a non-empty array (attempt %d/%d)",
                attempt, MAX_LLM_ATTEMPTS,
            )
            continue

        logger.info("Generated %d roadmap steps", len(roadmap))
        _cache_put(profile, roadmap)
        return roadmap, "rag"

    logger.warning(
        "Roadmap generation exhausted %d attempts; using template roadmap",
        MAX_LLM_ATTEMPTS,
    )
    return get_fallback_roadmap(profile), "template"


def roadmap_agent(state: AgentState) -> AgentState:
    """Generate compliance roadmap using RAG"""
    logger.info("Roadmap Agent running")

    profile = state.get("user_profile", {})

    if not profile:
        logger.warning("No user profile available")
        return state

    # Check if roadmap already exists
    if state.get("roadmap"):
        logger.info("Roadmap already generated, skipping")
        return state

    roadmap, source = generate_roadmap(profile)

    state["roadmap"] = roadmap
    state["roadmap_source"] = source
    # generate_roadmap always returns a roadmap, so the graph never has to
    # re-enter this node. Reset the counter so a later regeneration is clean.
    state["roadmap_retry_count"] = 0

    return state


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # Test the roadmap agent
    test_state = AgentState(
        messages=[],
        user_profile={
            "business_name": "Juan's Cafe",
            "business_type": "cafe",
            "location": "Sampaloc, Zone 30",
            "capital": 500000,
            "employees": 3,
            "serves_food": True,
            "entity_type": "Sole Proprietorship"
        },
        roadmap=[],
        documents=[],
        current_stage="profiling",
        rag_context=None,
        roadmap_retry_count=0,
        roadmap_source=None,
        error=None
    )

    result = roadmap_agent(test_state)

    print("\n" + "="*60)
    print(f"Test Result (source: {result.get('roadmap_source')}):")
    print("="*60)

    if result.get("roadmap"):
        for step in result["roadmap"][:3]:  # Show first 3 steps
            print(f"\n{step['step_number']}. {step['title']}")
            print(f"   {step['description'][:150]}...")
            print(f"   Cost: {step.get('estimated_cost', 'TBD')}")
            print(f"   Time: {step.get('estimated_time', 'TBD')}")
