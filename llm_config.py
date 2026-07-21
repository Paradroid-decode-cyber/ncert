"""
llm_config.py
─────────────────────────────────────────────────────────────────────────────
Unified LLM configuration for NCERT AI Tutor.

Usage:
    from llm_config import get_llm_response, get_vision_response, llm_info

    # Text generation
    reply = get_llm_response("Explain photosynthesis simply.")

    # Vision (image captioning) — only works when CLOUD_API=true
    caption = get_vision_response("Describe this diagram.", image_base64, "image/png")

Switch modes in .env:
    CLOUD_API=true   → OpenAI gpt-4o-mini
    CLOUD_API=false  → Local Phi-2 GGUF via llama-cpp
"""
from __future__ import annotations

import os
import logging
from typing import Optional
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("llm_config")

# ── Read env ──────────────────────────────────────────────────────────────────
CLOUD_API: bool         = os.getenv("CLOUD_API", "false").lower() == "true"
OPENAI_API_KEY: str     = os.getenv("OPENAI_API_KEY", "")
CLOUD_MODEL: str        = os.getenv("CLOUD_MODEL", "gpt-4o-mini")
CLOUD_MAX_TOKENS: int   = int(os.getenv("CLOUD_MAX_TOKENS", "1024"))
CLOUD_TEMPERATURE: float = float(os.getenv("CLOUD_TEMPERATURE", "0.3"))

LOCAL_MODEL_PATH: str   = os.getenv("LOCAL_MODEL_PATH", "./models/phi2-q8.gguf")
LOCAL_MODEL_CTX: int    = int(os.getenv("LOCAL_MODEL_CTX", "2048"))
LOCAL_MODEL_THREADS: int = int(os.getenv("LOCAL_MODEL_THREADS", "4"))
LOCAL_MAX_TOKENS: int   = int(os.getenv("LOCAL_MAX_TOKENS", "512"))
LOCAL_TEMPERATURE: float = float(os.getenv("LOCAL_TEMPERATURE", "0.3"))

VISION_ENABLED: bool    = os.getenv("VISION_ENABLED", "true").lower() == "true"

# ── Lazy singletons ───────────────────────────────────────────────────────────
_openai_client = None
_local_model   = None


# ─────────────────────────────────────────────────────────────────────────────
# Private: Provider initialisation
# ─────────────────────────────────────────────────────────────────────────────
def _get_openai_client():
    """Lazy-load OpenAI client. Raises clearly if key missing."""
    global _openai_client
    if _openai_client is None:
        if not OPENAI_API_KEY:
            raise EnvironmentError(
                "OPENAI_API_KEY is not set in .env but CLOUD_API=true.\n"
                "Either add your key or set CLOUD_API=false to use a local model."
            )
        try:
            from openai import OpenAI
            _openai_client = OpenAI(api_key=OPENAI_API_KEY)
            log.info(f"✅ OpenAI client ready  →  model: {CLOUD_MODEL}")
        except ImportError:
            raise ImportError(
                "openai package not installed. Run: pip install openai"
            )
    return _openai_client


def _get_local_model():
    """Lazy-load Phi-2 GGUF model via llama-cpp. Raises clearly if file missing."""
    global _local_model
    if _local_model is None:
        if not os.path.exists(LOCAL_MODEL_PATH):
            raise FileNotFoundError(
                f"Local model not found at: {LOCAL_MODEL_PATH}\n"
                "Download with:\n"
                "  wget https://huggingface.co/TheBloke/phi-2-GGUF/resolve/main/"
                "phi-2.Q8_0.gguf -O models/phi2-q8.gguf\n"
                "Or set CLOUD_API=true in .env to use OpenAI instead."
            )
        try:
            from llama_cpp import Llama
            log.info(f"⏳ Loading local model: {LOCAL_MODEL_PATH}  (first call ~3s)")
            _local_model = Llama(
                model_path  = LOCAL_MODEL_PATH,
                n_ctx       = LOCAL_MODEL_CTX,
                n_threads   = LOCAL_MODEL_THREADS,
                verbose     = False,
            )
            log.info(f"✅ Local model ready  →  {LOCAL_MODEL_PATH}")
        except ImportError:
            raise ImportError(
                "llama-cpp-python not installed. Run: pip install llama-cpp-python"
            )
    return _local_model


# ─────────────────────────────────────────────────────────────────────────────
# Private: Response generators
# ─────────────────────────────────────────────────────────────────────────────
def _cloud_text(
    prompt: str,
    system: Optional[str],
    max_tokens: int,
    temperature: float,
) -> str:
    client = _get_openai_client()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = client.chat.completions.create(
        model       = CLOUD_MODEL,
        messages    = messages,
        max_tokens  = max_tokens,
        temperature = temperature,
    )
    return resp.choices[0].message.content.strip()


def _cloud_vision(
    prompt: str,
    image_b64: str,
    media_type: str,
    max_tokens: int,
) -> str:
    """GPT-4o-mini vision call for image captioning."""
    client = _get_openai_client()
    resp = client.chat.completions.create(
        model = CLOUD_MODEL,
        messages = [{
            "role": "user",
            "content": [
                {"type": "text",       "text": prompt},
                {"type": "image_url",  "image_url": {
                    "url": f"data:{media_type};base64,{image_b64}"
                }},
            ],
        }],
        max_tokens = max_tokens,
    )
    return resp.choices[0].message.content.strip()


def _local_text(
    prompt: str,
    system: Optional[str],
    max_tokens: int,
    temperature: float,
) -> str:
    model = _get_local_model()
    # Local model has no system role — prepend as token block
    if system:
        full_prompt = f"[SYSTEM]\n{system}\n\n[USER]\n{prompt}\n\n[ASSISTANT]\n"
    else:
        full_prompt = f"[USER]\n{prompt}\n\n[ASSISTANT]\n"

    out = model(
        full_prompt,
        max_tokens  = max_tokens,
        temperature = temperature,
        stop        = ["[USER]", "[SYSTEM]", "\n\n\n"],
        echo        = False,
    )
    return out["choices"][0]["text"].strip()


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def get_llm_response(
    prompt:      str,
    system:      Optional[str] = None,
    max_tokens:  Optional[int] = None,
    temperature: Optional[float] = None,
) -> str:
    """
    Generate a text response from the configured LLM.

    Automatically routes to:
      CLOUD_API=true  → OpenAI gpt-4o-mini
      CLOUD_API=false → Local Phi-2 GGUF

    Args:
        prompt      : User/instruction prompt text
        system      : Optional system message
        max_tokens  : Override default max_tokens from .env
        temperature : Override default temperature from .env

    Returns:
        Response string

    Raises:
        EnvironmentError  : Missing API key (cloud mode)
        FileNotFoundError : Model file missing (local mode)
        ImportError       : Required package not installed
    """
    mt   = max_tokens  if max_tokens  is not None else (CLOUD_MAX_TOKENS if CLOUD_API else LOCAL_MAX_TOKENS)
    temp = temperature if temperature is not None else (CLOUD_TEMPERATURE if CLOUD_API else LOCAL_TEMPERATURE)

    if CLOUD_API:
        return _cloud_text(prompt, system, mt, temp)
    else:
        return _local_text(prompt, system, mt, temp)


def get_vision_response(
    prompt:     str,
    image_b64:  str,
    media_type: str = "image/png",
    max_tokens: int = 300,
) -> Optional[str]:
    """
    Generate a caption/description for an image.

    Only works when CLOUD_API=true and VISION_ENABLED=true.
    Returns None if vision is disabled or unavailable.

    Args:
        prompt     : Text instruction (e.g. "Describe this NCERT diagram")
        image_b64  : Base64-encoded image bytes
        media_type : MIME type — "image/png" | "image/jpeg" | "image/webp"
        max_tokens : Max caption length in tokens

    Returns:
        Caption string, or None if vision unavailable
    """
    if not CLOUD_API:
        log.debug("Vision skipped — CLOUD_API=false (local model has no vision)")
        return None
    if not VISION_ENABLED:
        log.debug("Vision skipped — VISION_ENABLED=false")
        return None

    return _cloud_vision(prompt, image_b64, media_type, max_tokens)


def llm_info() -> dict:
    """
    Return current LLM configuration as a dict.
    Useful for /health endpoint and logging.

    Returns:
        {provider, model, cloud_api, vision_enabled, max_tokens, temperature}
    """
    return {
        "provider":       "openai"          if CLOUD_API else "local",
        "model":          CLOUD_MODEL       if CLOUD_API else LOCAL_MODEL_PATH,
        "cloud_api":      CLOUD_API,
        "vision_enabled": VISION_ENABLED and CLOUD_API,
        "max_tokens":     CLOUD_MAX_TOKENS  if CLOUD_API else LOCAL_MAX_TOKENS,
        "temperature":    CLOUD_TEMPERATURE if CLOUD_API else LOCAL_TEMPERATURE,
    }


def warm_up() -> bool:
    """
    Pre-load the LLM (avoid cold-start latency on first real request).
    Call once at application startup.

    Returns:
        True if successful, False if initialisation failed
    """
    try:
        if CLOUD_API:
            _get_openai_client()
        else:
            _get_local_model()
        return True
    except Exception as e:
        log.error(f"LLM warm-up failed: {e}")
        return False
