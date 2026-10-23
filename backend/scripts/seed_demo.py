"""
Create (or refresh) the demo account, so a live demo never starts from an
empty form or depends on onboarding going smoothly on stage.

Run with the backend up:
    uv run python scripts/seed_demo.py

Then sign in on the landing page with the printed email and password. The
roadmap is built fresh each run, with Stage 1 (DTI) already marked done.
"""
import os
import sys

import httpx

API = os.getenv("SELLYO_API", "http://127.0.0.1:8000/api")
EMAIL = os.getenv("DEMO_EMAIL", "demo@sellyo.ph")
PASSWORD = os.getenv("DEMO_PASSWORD", "sellyo-demo-2026")

PROFILE = {
    "business_name": "Manila Artisanal Cafe",
    "business_type": "Small Café / Food Service",
    "location": "Sampaloc, Zone 30, City of Manila",
    "capital": 150000,
    "employees": 4,
    "serves_food": True,
    "has_signage": True,
    "is_homebased": False,
    "entity_type": "Sole Proprietorship",
    "owner_age": 26,
}


def main() -> int:
    client = httpx.Client(base_url=API, timeout=180)

    res = client.post("/auth/signup", json={"email": EMAIL, "password": PASSWORD, "name": "Juan Dela Cruz"})
    if res.status_code == 409:
        res = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if res.status_code >= 400:
        print(f"Could not sign in as {EMAIL}: {res.status_code} {res.text}")
        return 1
    token = res.json()["token"]
    auth = {"Authorization": f"Bearer {token}"}

    session_id = client.post("/session", json={}).json()["session_id"]
    roadmap = client.post("/roadmap", json={"session_id": session_id, "profile": PROFILE}).json()
    steps = roadmap["roadmap"]

    # Start the demo at Stage 2, so the upload check has something to show.
    client.put(f"/session/{session_id}/progress", json={"completed": ["step-1"], "checked": []})
    client.put("/auth/workspace", json={"session_id": session_id}, headers=auth).raise_for_status()

    print(f"Demo account ready ({roadmap.get('source')} roadmap, {len(steps)} stages):")
    for step in steps:
        print(f"  {step['step_number']}. {step['title']}")
    print(f"\n  Email:    {EMAIL}\n  Password: {PASSWORD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
