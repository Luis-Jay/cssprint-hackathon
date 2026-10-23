"""
Authentication routes

Opaque bearer tokens backed by SQLite. Signup and login return a token the
client sends as `Authorization: Bearer <token>`; only the token's hash is
stored server-side.
"""
import logging
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.concurrency import run_in_threadpool

import db
from api.models import (
    AuthResponse, LoginRequest, SignupRequest, UserResponse, WorkspaceRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 8


async def current_user(authorization: Optional[str] = Header(None)) -> dict:
    """
    Resolve the bearer token into a user, or 401.

    Use as a dependency on any route that needs a signed-in caller.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not signed in",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1].strip()
    # PBKDF2 and SQLite are both blocking; keep them off the event loop.
    user = await run_in_threadpool(db.resolve_auth_session, token)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user["token"] = token
    return user


def _validate(email: str, password: str) -> None:
    if not EMAIL_RE.match(email.strip()):
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    if len(password) < MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=422,
            detail=f"Password must be at least {MIN_PASSWORD_LEN} characters",
        )


def _auth_response(user: dict, token: str, session_id: Optional[str]) -> AuthResponse:
    return AuthResponse(
        token=token,
        user=UserResponse(id=user["id"], email=user["email"], name=user["name"]),
        session_id=session_id,
    )


@router.post("/signup", response_model=AuthResponse, status_code=201)
async def signup(request: SignupRequest):
    """Create an account and sign in."""
    _validate(request.email, request.password)

    name = (request.name or "").strip() or request.email.split("@")[0]

    try:
        user = await run_in_threadpool(
            db.create_user, request.email.strip(), name, request.password
        )
    except db.EmailAlreadyRegistered:
        raise HTTPException(
            status_code=409, detail="That email is already registered - try logging in"
        )

    token = await run_in_threadpool(db.create_auth_session, user["id"])
    logger.info("Account created: user_id=%s", user["id"])
    return _auth_response(user, token, None)


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """Sign in to an existing account."""
    user = await run_in_threadpool(db.authenticate, request.email, request.password)

    if user is None:
        # One message for both unknown-address and wrong-password, so the
        # endpoint does not confirm which addresses are registered.
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    token = await run_in_threadpool(db.create_auth_session, user["id"])
    session_id = await run_in_threadpool(db.get_workspace, user["id"])
    logger.info("Login: user_id=%s workspace=%s", user["id"], session_id)
    return _auth_response(user, token, session_id)


@router.get("/me", response_model=AuthResponse)
async def me(user: dict = Depends(current_user)):
    """Who is this token, and which workspace do they own."""
    session_id = await run_in_threadpool(db.get_workspace, user["id"])
    return _auth_response(user, user["token"], session_id)


@router.post("/logout", status_code=204)
async def logout(user: dict = Depends(current_user)):
    """Invalidate the caller's token."""
    await run_in_threadpool(db.delete_auth_session, user["token"])
    logger.info("Logout: user_id=%s", user["id"])


@router.put("/workspace", response_model=AuthResponse)
async def link_workspace(
    request: WorkspaceRequest,
    user: dict = Depends(current_user),
):
    """
    Attach an agent session to the signed-in user.

    Called after onboarding so that logging in on another device restores the
    same roadmap rather than starting from scratch.
    """
    await run_in_threadpool(db.set_workspace, user["id"], request.session_id)
    return _auth_response(user, user["token"], request.session_id)
