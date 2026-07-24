import os
import re
import json
import time

import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("LLM_API_BASE_URL", "http://192.168.68.58:8642/v1/chat/completions")
API_KEY = os.getenv("LLM_API_KEY")
MODEL_NAME = os.getenv("LLM_MODEL", "hermes-agent") 

# This endpoint is a self-hosted/local model, so per-token cost defaults to 0.
# Set these in .env if you want to model an actual cost (e.g. amortized GPU/electricity).
INPUT_COST_PER_1K_USD = float(os.getenv("INPUT_COST_PER_1K_USD", "0"))
OUTPUT_COST_PER_1K_USD = float(os.getenv("OUTPUT_COST_PER_1K_USD", "0"))
USD_TO_INR = float(os.getenv("USD_TO_INR", "86"))

MAX_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = 2
# Local models can be slow (cold start / no GPU) — observed ~40-60s for this endpoint.
REQUEST_TIMEOUT_SECONDS = int(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "120"))


def estimate_tokens(text):
    """Rough heuristic (~1.3 tokens/word) used when the API doesn't report usage."""
    if not text:
        return 0
    return max(1, round(len(text.split()) * 1.3))


def _extract_json(raw_text):
    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def call_llm(prompt, system_prompt=None):
    """Calls the OpenAI-compatible /v1/chat/completions endpoint and returns
    (narrative_dict, input_tokens, output_tokens).

    Retries on transient errors (timeouts, connection issues, malformed JSON)
    with a short backoff, since the endpoint is a single local model instance
    without the elastic capacity of a hosted API.
    """
    if not API_KEY:
        raise RuntimeError("LLM_API_KEY not set. Add it to backend/.env")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {"model": MODEL_NAME, "messages": messages}
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                API_BASE_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS
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
            print(f"[LLM] Attempt {attempt}/{MAX_RETRIES} failed: {type(e).__name__}: {e}", flush=True)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
                continue

    raise RuntimeError(f"LLM call failed after {MAX_RETRIES} attempts: {last_error}")


def calculate_cost(input_tokens, output_tokens):
    cost_usd = (input_tokens / 1000) * INPUT_COST_PER_1K_USD + (output_tokens / 1000) * OUTPUT_COST_PER_1K_USD
    cost_inr = cost_usd * USD_TO_INR
    return round(cost_usd, 6), round(cost_inr, 4)
