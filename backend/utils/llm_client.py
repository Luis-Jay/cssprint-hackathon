"""
Settings and the shared Google Gemini client used by every agent.

Agents call get_llm_client().invoke_model(...) and receive {"content": text};
none of them know which model answered.
"""
import os
import threading
import time
from functools import lru_cache
from typing import Optional, Dict, Any
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import httpx

load_dotenv()


class Settings(BaseSettings):
    """App configuration, read from the environment and .env"""

    # Google Gemini (free tier via Google AI Studio)
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    # Flash-Lite answers in about a second; full Flash took 18-60s or
    # returned 503 under free-tier load. Flash is tried when Lite is busy.
    gemini_model_id: str = os.getenv("GEMINI_MODEL_ID", "gemini-flash-lite-latest")
    gemini_fallback_model_id: str = os.getenv("GEMINI_FALLBACK_MODEL_ID", "gemini-flash-latest")
    gemini_endpoint: str = os.getenv("GEMINI_ENDPOINT", "https://generativelanguage.googleapis.com/v1beta")
    # Per-model read timeout. The upload request waits on up to two model
    # calls, and the browser gives up after 120s.
    gemini_timeout_seconds: float = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "25"))
    # Blank leaves the model's default. Flash-Lite rejects "0" with a 400.
    gemini_thinking_budget: str = os.getenv("GEMINI_THINKING_BUDGET", "")

    # Local model used when building an index. Searching always uses the model
    # recorded in the index's meta.json. Changing this needs a reindex.
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")

    # Model Parameters (ZERO HALLUCINATION MODE)
    max_tokens: int = int(os.getenv("MAX_TOKENS", "2048"))
    temperature: float = float(os.getenv("TEMPERATURE", "0.0"))

    # RAG Configuration
    top_k_results: int = int(os.getenv("TOP_K_RESULTS", "3"))
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "800"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "150"))

    # Caching
    enable_cache: bool = os.getenv("ENABLE_CACHE", "true").lower() == "true"
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))

    # Server Configuration (optional)
    backend_port: int = int(os.getenv("BACKEND_PORT", "8000"))
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Allow extra fields from .env


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Singleton settings.

    pydantic-settings re-reads and re-parses .env on every construction, and
    all three agents were building a fresh settings object per invocation.
    """
    return Settings()


_PLACEHOLDERS = {"your_api_key_here", "your_gemini_api_key_here", "changeme"}


def llm_is_configured() -> bool:
    """Whether a real (non-placeholder) Gemini API key is set."""
    key = get_settings().gemini_api_key.strip()
    return bool(key and key.lower() not in _PLACEHOLDERS)


# Shared connection pool. Building a fresh httpx.Client per agent call meant a
# new TCP + TLS handshake on every single invocation (~100-300ms).
_shared_http_client: Optional[httpx.Client] = None
_http_client_lock = threading.Lock()


def _get_http_client() -> httpx.Client:
    """Process-wide pooled HTTP client."""
    global _shared_http_client
    if _shared_http_client is None:
        with _http_client_lock:
            if _shared_http_client is None:  # double-checked under the lock
                _shared_http_client = httpx.Client(
                    timeout=httpx.Timeout(60.0, connect=10.0),
                    limits=httpx.Limits(
                        max_connections=20,
                        max_keepalive_connections=10,
                    ),
                )
    return _shared_http_client


class GeminiClient:
    """Google Gemini via the generateContent REST API."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        http_client: Optional[httpx.Client] = None
    ):
        self.settings = settings or get_settings()
        # Only a caller-supplied client is owned (and therefore closed) by this
        # instance; the default is the shared pool, which outlives the request.
        self._owns_client = http_client is not None
        self.client = http_client or _get_http_client()

    def invoke_model(self, prompt: str, system_prompt: Optional[str] = None,
                     max_tokens: Optional[int] = None,
                     attachments: Optional[list] = None) -> Dict[str, Any]:
        model_id = self.settings.gemini_model_id

        # Key in a header, not the query string, so it never lands in logs.
        headers = {
            "x-goog-api-key": self.settings.gemini_api_key,
            "Content-Type": "application/json",
        }

        # Images first: the model attends better to a question asked after
        # the evidence. Gemini reads both images and PDFs from inline data.
        parts = [
            {"inline_data": {"mime_type": a["media_type"], "data": a["data"]}}
            for a in (attachments or [])
        ]
        parts.append({"text": prompt})

        generation_config: Dict[str, Any] = {
            "maxOutputTokens": max_tokens or self.settings.max_tokens,
            "temperature": self.settings.temperature,
        }
        budget = self.settings.gemini_thinking_budget.strip()
        if budget:
            generation_config["thinkingConfig"] = {"thinkingBudget": int(budget)}

        body: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": generation_config,
        }
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        # Import here: observability imports this module for redaction, and a
        # top-level import would close the cycle.
        import observability as obs

        obs.emit(
            "model", f"Calling {model_id}",
            phase_detail="request",
            model=model_id,
            max_tokens=generation_config["maxOutputTokens"],
            temperature=generation_config["temperature"],
            system_prompt=system_prompt or "",
            prompt=prompt,
            prompt_chars=len(prompt),
            attachments=[a["kind"] for a in (attachments or [])],
        )

        started = time.perf_counter()
        try:
            result = self._generate(headers, body)

            candidates = result.get("candidates") or []
            if not candidates:
                feedback = result.get("promptFeedback", {})
                raise ValueError(f"No candidates returned: {feedback or result}")

            candidate = candidates[0]
            text = "".join(
                p.get("text", "")
                for p in candidate.get("content", {}).get("parts", [])
                if not p.get("thought")
            )
            if not text:
                raise ValueError(
                    f"Empty response (finishReason={candidate.get('finishReason')})"
                )

            meta = result.get("usageMetadata", {})
            usage = {"input_tokens": meta.get("promptTokenCount"),
                     "output_tokens": meta.get("candidatesTokenCount")}
            model = result.get("modelVersion", model_id)
            obs.emit(
                "model", "Model responded",
                duration_ms=(time.perf_counter() - started) * 1000,
                model=model,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                response_chars=len(text),
                # The raw, pre-parse text. This is the "actual output" -
                # everything downstream is derived from it.
                raw_response=text,
            )
            return {"content": text, "usage": usage, "model": model}

        except httpx.HTTPStatusError as e:
            obs.emit("model", "Gemini returned an error", status="error",
                     duration_ms=(time.perf_counter() - started) * 1000,
                     http_status=e.response.status_code, body=e.response.text[:500])
            raise Exception(f"Gemini API error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            obs.emit("model", "Gemini call failed", status="error",
                     duration_ms=(time.perf_counter() - started) * 1000,
                     error=f"{type(e).__name__}: {e}")
            raise Exception(f"Failed to call Gemini: {str(e)}")

    def _generate(self, headers: Dict[str, str], body: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST to the primary model, moving to the fallback when it is busy.

        Free-tier models return 503 or 429 under load, or simply hang; the
        same request usually succeeds at once on the other model.
        """
        import observability as obs

        models = [self.settings.gemini_model_id]
        fallback = self.settings.gemini_fallback_model_id.strip()
        if fallback and fallback not in models:
            models.append(fallback)

        timeout = httpx.Timeout(self.settings.gemini_timeout_seconds, connect=10.0)
        for i, model_id in enumerate(models):
            url = f"{self.settings.gemini_endpoint}/models/{model_id}:generateContent"
            last = i == len(models) - 1
            try:
                response = self.client.post(url, headers=headers, json=body,
                                            timeout=timeout)
                if response.status_code in (429, 500, 503) and not last:
                    obs.emit("model", f"{model_id} busy - trying {models[i + 1]}",
                             status="warn", http_status=response.status_code)
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException:
                if last:
                    raise
                obs.emit("model", f"{model_id} timed out - trying {models[i + 1]}",
                         status="warn")
        raise RuntimeError("no Gemini model configured")

    def close(self):
        """
        Close the HTTP client, if this instance owns one.

        Instances using the shared pool leave it open on purpose - closing it
        would force a fresh TLS handshake on the next agent call.
        """
        if self._owns_client:
            self.client.close()


_llm_client: Optional[GeminiClient] = None
_llm_client_lock = threading.Lock()


def get_llm_client() -> GeminiClient:
    """
    Get the shared Gemini client.

    Prefer this over constructing GeminiClient directly so every agent reuses
    one settings object and one connection pool.
    """
    global _llm_client
    if _llm_client is None:
        with _llm_client_lock:
            if _llm_client is None:  # double-checked under the lock
                _llm_client = GeminiClient(get_settings())
    return _llm_client


def shutdown_llm_client() -> None:
    """
    Close the shared connection pool. Called from the app lifespan hook.

    Also drops the cached client. Without that, the singleton kept holding the
    httpx client we just closed, so anything that started the app again in the
    same process (tests, an embedded worker) got "Cannot send a request, as
    the client has been closed" on every call.
    """
    global _shared_http_client, _llm_client
    with _http_client_lock:
        if _shared_http_client is not None:
            _shared_http_client.close()
            _shared_http_client = None
    with _llm_client_lock:
        _llm_client = None


if __name__ == "__main__":
    settings = get_settings()
    print(f"Gemini configured: {'Yes' if llm_is_configured() else 'No'}")
    print(f"Model: {settings.gemini_model_id} (fallback: {settings.gemini_fallback_model_id})")
    print(f"Temperature: {settings.temperature}")
    print(f"Max Tokens: {settings.max_tokens}")
