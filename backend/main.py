"""
Sellyo Backend - FastAPI Application
Main entry point for the API server
"""
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Windows consoles default to cp1252, which cannot encode the peso sign or arrows that appear in
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("permitpal")

import db
from api.auth import router as auth_router
from api.routes import router
from rag.retriever import get_retriever
from utils.llm_client import shutdown_llm_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Warm the RAG retriever at boot.

    Constructing it costs ~7s (FAISS load is 28ms of that; the rest is the
    all-MiniLM-L6-v2 SentenceTransformer). Paying it here means no user ever
    waits for it, and concurrent first requests cannot race to build two.
    """
    db.init_db()
    purged = db.purge_expired_sessions()
    logger.info("Database ready (%d expired auth sessions purged)", purged)

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, get_retriever)
        logger.info("RAG retriever warm - roadmap generation will not pay model load")
    except Exception:
        # A cold retriever is not fatal: generate_roadmap falls back to the
        # template roadmap, so the API still serves.
        logger.exception("RAG warm-up failed; roadmaps will use the template fallback")

    yield

    shutdown_llm_client()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Sellyo API",
    description="Backend API for Manila business permit compliance assistance",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Configuration
_default_origins = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001"
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip() for o in os.getenv("CORS_ORIGINS", _default_origins).split(",") if o.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(auth_router, prefix="/api")
app.include_router(router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Sellyo API",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/docs"
    }


def main():
    """Run the FastAPI server"""
    host = os.getenv("BACKEND_HOST", "127.0.0.1")
    port = int(os.getenv("BACKEND_PORT", "8000"))
    reload = os.getenv("BACKEND_RELOAD", "true").lower() == "true"

    print("Starting Sellyo Backend Server...")
    print(f"API Documentation: http://{host}:{port}/docs")
    print(f"Health Check:      http://{host}:{port}/api/health")
    if reload:
        print("Reload is ON - the RAG model reloads (~7s) on every code change.")

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
