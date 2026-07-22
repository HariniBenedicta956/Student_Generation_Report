import os
import re
import json
import time

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

_client = genai.Client(api_key=API_KEY) if API_KEY else None

# Approximate Gemini Flash pricing (USD per 1K tokens). Adjust via .env if rates change.
INPUT_COST_PER_1K_USD = float(os.getenv("INPUT_COST_PER_1K_USD", "0.000075"))
OUTPUT_COST_PER_1K_USD = float(os.getenv("OUTPUT_COST_PER_1K_USD", "0.0003"))
USD_TO_INR = float(os.getenv("USD_TO_INR", "86"))

MAX_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = 2


def estimate_tokens(text):
    """Rough heuristic (~1.3 tokens/word) used when the API doesn't report usage_metadata."""
    if not text:
        return 0
    return max(1, round(len(text.split()) * 1.3))


def _extract_json(raw_text):
    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def call_gemini_flash(prompt, system_prompt=None):
    """Calls Gemini Flash and returns (narrative_dict, input_tokens, output_tokens).

    Retries on transient/rate-limit errors with exponential backoff, since Gemini
    Flash free-tier keys enforce requests-per-minute limits during batch processing.
    """
    if not _client:
        raise RuntimeError("GEMINI_API_KEY not set. Add it to backend/.env")

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
    )

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = _client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=config,
            )
            raw = response.text
            narrative = _extract_json(raw)

            usage = getattr(response, "usage_metadata", None)
            if usage and usage.prompt_token_count is not None:
                input_tokens = usage.prompt_token_count
                output_tokens = usage.candidates_token_count or estimate_tokens(raw)
            else:
                input_tokens = estimate_tokens(prompt)
                output_tokens = estimate_tokens(raw)

            return narrative, input_tokens, output_tokens

        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
                continue

    raise RuntimeError(f"Gemini Flash call failed after {MAX_RETRIES} attempts: {last_error}")


def calculate_cost(input_tokens, output_tokens):
    cost_usd = (input_tokens / 1000) * INPUT_COST_PER_1K_USD + (output_tokens / 1000) * OUTPUT_COST_PER_1K_USD
    cost_inr = cost_usd * USD_TO_INR
    return round(cost_usd, 6), round(cost_inr, 4)
