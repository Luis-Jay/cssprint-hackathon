"""
Shared JSON extraction for LLM responses

All three agents ask Claude for raw JSON and then have to cope with markdown
fences and stray prose. That unwrapping logic was duplicated verbatim in
profiling_agent, roadmap_agent and inspection_agent.
"""
import json
from typing import Any


def extract_json(content: str) -> Any:
    """Pull a JSON value out of a model response."""
    if not content or not content.strip():
        raise json.JSONDecodeError("Empty model response", content or "", 0)

    text = content.strip()

    # Strip markdown fences if present
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fall back to the outermost array or object embedded in the text
        for opener, closer in (("[", "]"), ("{", "}")):
            start = text.find(opener)
            end = text.rfind(closer)
            if start != -1 and end > start:
                return json.loads(text[start:end + 1])
        raise
