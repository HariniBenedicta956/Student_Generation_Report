import os
import re
import json
import time

import requests
from dotenv import load_dotenv

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover - handled at runtime
    genai = None
    types = None

load_dotenv()

USD_TO_INR = float(os.getenv("USD_TO_INR", "86"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "120"))
MAX_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = 2

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


def _cost(name, default):
    return float(os.getenv(name, default))


# Each entry describes one selectable model configuration. "kind" picks which
# _call_* function handles the request; everything else is provider-specific
# config read from .env (see .env.example).
PROVIDERS = {
    "hermes": {
        "label": "Hermes (self-hosted)",
        "kind": "openai_chat",
        "base_url": os.getenv("HERMES_API_BASE_URL", "http://192.168.68.58:8642/v1/chat/completions"),
        "api_key": os.getenv("HERMES_API_KEY"),
        "model": os.getenv("HERMES_MODEL", "hermes-agent"),
        "input_cost": _cost("HERMES_INPUT_COST_PER_1K_USD", "0"),
        "output_cost": _cost("HERMES_OUTPUT_COST_PER_1K_USD", "0"),
    },
    "gemini_flash": {
        "label": "Gemini Flash",
        "kind": "gemini",
        "api_key": GEMINI_API_KEY,
        "model": os.getenv("GEMINI_FLASH_MODEL", "gemini-flash-latest"),
        "input_cost": _cost("GEMINI_FLASH_INPUT_COST_PER_1K_USD", "0.000075"),
        "output_cost": _cost("GEMINI_FLASH_OUTPUT_COST_PER_1K_USD", "0.0003"),
    },
    "gemini_pro": {
        "label": "Gemini Pro",
        "kind": "gemini",
        "api_key": GEMINI_API_KEY,
        "model": os.getenv("GEMINI_PRO_MODEL", "gemini-2.5-pro"),
        "input_cost": _cost("GEMINI_PRO_INPUT_COST_PER_1K_USD", "0.00125"),
        "output_cost": _cost("GEMINI_PRO_OUTPUT_COST_PER_1K_USD", "0.005"),
    },
    "ollama_hermes3": {
        "label": "Ollama - Hermes3 8B",
        "kind": "ollama",
        "base_url": os.getenv("OLLAMA_API_BASE_URL", "http://192.168.68.58:11434"),
        "model": os.getenv("OLLAMA_HERMES3_MODEL", "hermes3:8b"),
        "input_cost": _cost("OLLAMA_INPUT_COST_PER_1K_USD", "0"),
        "output_cost": _cost("OLLAMA_OUTPUT_COST_PER_1K_USD", "0"),
    },
    "ollama_llama3": {
        "label": "Ollama - Llama3 8B",
        "kind": "ollama",
        "base_url": os.getenv("OLLAMA_API_BASE_URL", "http://192.168.68.58:11434"),
        "model": os.getenv("OLLAMA_LLAMA3_MODEL", "llama3:8b"),
        "input_cost": _cost("OLLAMA_INPUT_COST_PER_1K_USD", "0"),
        "output_cost": _cost("OLLAMA_OUTPUT_COST_PER_1K_USD", "0"),
    },
}

_configured_keys = [k.strip() for k in os.getenv("LLM_PROVIDERS", "").split(",") if k.strip()]
ENABLED_PROVIDERS = [k for k in _configured_keys if k in PROVIDERS] or list(PROVIDERS.keys())

DEFAULT_PROVIDER = os.getenv("DEFAULT_LLM_PROVIDER", "").strip() or ENABLED_PROVIDERS[0]


def list_providers():
    """Returns [{key, label}] for enabled providers, in display order — used by the frontend selector."""
    return [{"key": k, "label": PROVIDERS[k]["label"]} for k in ENABLED_PROVIDERS]


def estimate_tokens(text):
    """Rough heuristic (~1.3 tokens/word) used when the API doesn't report usage."""
    if not text:
        return 0
    return max(1, round(len(text.split()) * 1.3))


# Narrative fields the prompt asks for as a single string vs. a list of bullets.
# Smaller/local models (e.g. Ollama's llama3) don't always follow that shape as
# reliably as Gemini/Hermes, so normalize here once for every provider rather
# than letting reportlab blow up deep in PDF rendering.
_STRING_FIELDS = ("summary", "career_guidance", "overall_insight")
_LIST_FIELDS = ("strengths", "improvements", "recommendations")


def _flatten_to_text(value):
    if isinstance(value, list):
        return " ".join(_flatten_to_text(v) for v in value)
    return "" if value is None else str(value)


def _normalize_narrative(data):
    if not isinstance(data, dict):
        return data
    for field in _STRING_FIELDS:
        if isinstance(data.get(field), list):
            data[field] = _flatten_to_text(data[field])
    for field in _LIST_FIELDS:
        value = data.get(field)
        if isinstance(value, str):
            data[field] = [value]
        elif isinstance(value, list):
            data[field] = [_flatten_to_text(item) for item in value]
    data["custom_sections"] = _normalize_custom_sections(data.get("custom_sections"))
    return data


def _normalize_custom_sections(sections):
    """Coerces whatever shape the model returned for custom_sections into a
    clean list of {heading, content} dicts, dropping anything empty."""
    if isinstance(sections, dict):
        sections = [sections]
    if not isinstance(sections, list):
        return [{"heading": "Additional Details", "content": _flatten_to_text(sections)}] if sections else []

    normalized = []
    for item in sections:
        if isinstance(item, dict):
            heading = _flatten_to_text(item.get("heading") or item.get("title") or "")
            content = _flatten_to_text(item.get("content") or item.get("body") or item.get("text") or "")
        else:
            heading, content = "", _flatten_to_text(item)
        if heading or content:
            normalized.append({"heading": heading or "Additional Details", "content": content})
    return normalized


def _extract_json(raw_text):
    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return _normalize_narrative(json.loads(text))


def _call_gemini(cfg, prompt, system_prompt=None):
    if not cfg["api_key"]:
        raise RuntimeError("GEMINI_API_KEY not set. Add it to backend/.env")
    if genai is None or types is None:
        raise RuntimeError("google-genai is not installed. Run pip install -r requirements.txt")

    client = genai.Client(api_key=cfg["api_key"])
    config = types.GenerateContentConfig(
        system_instruction=system_prompt or "",
        response_mime_type="application/json",
    )
    response = client.models.generate_content(model=cfg["model"], contents=prompt, config=config)

    raw = response.text
    narrative = _extract_json(raw)

    usage = getattr(response, "usage_metadata", None)
    input_tokens = getattr(usage, "prompt_token_count", None) if usage is not None else None
    output_tokens = getattr(usage, "candidates_token_count", None) if usage is not None else None

    input_tokens = input_tokens if input_tokens is not None else estimate_tokens(prompt)
    output_tokens = output_tokens if output_tokens is not None else estimate_tokens(raw)
    return narrative, input_tokens, output_tokens


def _call_openai_chat(cfg, prompt, system_prompt=None):
    """Generic OpenAI-style /chat/completions caller — used for the self-hosted Hermes endpoint."""
    if not cfg["api_key"]:
        raise RuntimeError(f"API key not set for provider '{cfg['label']}'. Add it to backend/.env")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {"model": cfg["model"], "messages": messages}
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                cfg["base_url"], headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            data = response.json()
            raw = data["choices"][0]["message"]["content"]
            narrative = _extract_json(raw)

            usage = data.get("usage") or {}
            input_tokens = usage.get("prompt_tokens") or estimate_tokens(prompt)
            output_tokens = usage.get("completion_tokens") or estimate_tokens(raw)

            return narrative, input_tokens, output_tokens

        except Exception as e:
            last_error = e
            print(f"[{cfg['label']}] Attempt {attempt}/{MAX_RETRIES} failed: {type(e).__name__}: {e}", flush=True)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
                continue

    raise RuntimeError(f"{cfg['label']} call failed after {MAX_RETRIES} attempts: {last_error}")


def _call_ollama(cfg, prompt, system_prompt=None):
    """Ollama's native /api/chat — no API key; token usage comes back as eval counts."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {"model": cfg["model"], "messages": messages, "stream": False, "format": "json"}
    url = cfg["base_url"].rstrip("/") + "/api/chat"

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            data = response.json()
            raw = data["message"]["content"]
            narrative = _extract_json(raw)

            input_tokens = data.get("prompt_eval_count") or estimate_tokens(prompt)
            output_tokens = data.get("eval_count") or estimate_tokens(raw)

            return narrative, input_tokens, output_tokens

        except Exception as e:
            last_error = e
            print(f"[{cfg['label']}] Attempt {attempt}/{MAX_RETRIES} failed: {type(e).__name__}: {e}", flush=True)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
                continue

    raise RuntimeError(f"{cfg['label']} call failed after {MAX_RETRIES} attempts: {last_error}")


_CALLERS = {
    "gemini": _call_gemini,
    "openai_chat": _call_openai_chat,
    "ollama": _call_ollama,
}


def call_llm(prompt, system_prompt=None, provider=None):
    """Calls the given provider key (or DEFAULT_PROVIDER) and returns (narrative_dict, input_tokens, output_tokens)."""
    key = provider or DEFAULT_PROVIDER
    cfg = PROVIDERS.get(key)
    if cfg is None:
        raise RuntimeError(f"Unknown LLM provider '{key}'. Available: {', '.join(PROVIDERS)}")
    return _CALLERS[cfg["kind"]](cfg, prompt, system_prompt)


def calculate_cost(input_tokens, output_tokens, provider=None):
    key = provider or DEFAULT_PROVIDER
    cfg = PROVIDERS.get(key, {})
    input_rate = cfg.get("input_cost", 0)
    output_rate = cfg.get("output_cost", 0)

    cost_usd = (input_tokens / 1000) * input_rate + (output_tokens / 1000) * output_rate
    cost_inr = cost_usd * USD_TO_INR
    return round(cost_usd, 6), round(cost_inr, 4)
