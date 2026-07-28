"""One-off evaluation harness: runs the same 5 students through both Gemini
(gemini-flash-latest) and the local Hermes endpoint (llm_client.py), in
parallel with each other, and records timing/tokens/cost/PDF output for
side-by-side comparison. Not part of the live app (app.py uses llm_client.py
only) — rerun this manually any time you want to re-compare providers.
"""
import os
import sys
import json
import time
import functools
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types

from prompt import SYSTEM_PROMPT, build_prompt
from pdf_generator import generate_pdf
import llm_client

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
GEMINI_INPUT_COST_PER_1K = float(os.getenv("GEMINI_INPUT_COST_PER_1K_USD", "0.000075"))
GEMINI_OUTPUT_COST_PER_1K = float(os.getenv("GEMINI_OUTPUT_COST_PER_1K_USD", "0.0003"))
USD_TO_INR = float(os.getenv("USD_TO_INR", "86"))

_gemini_client = genai.Client(api_key=GEMINI_API_KEY)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
STUDENTS_PATH = os.path.join(ROOT_DIR, "data", "students.json")
OUT_DIR = os.path.join(ROOT_DIR, "output", "comparison")

results = []
results_lock = threading.Lock()


def call_gemini(prompt, system_prompt):
    config = types.GenerateContentConfig(system_instruction=system_prompt, response_mime_type="application/json")
    response = _gemini_client.models.generate_content(model=GEMINI_MODEL, contents=prompt, config=config)
    narrative = llm_client._extract_json(response.text)
    usage = response.usage_metadata
    input_tokens = usage.prompt_token_count if usage else llm_client.estimate_tokens(prompt)
    output_tokens = usage.candidates_token_count if usage else llm_client.estimate_tokens(response.text)
    return narrative, input_tokens, output_tokens


def gemini_cost(input_tokens, output_tokens):
    cost_usd = (input_tokens / 1000) * GEMINI_INPUT_COST_PER_1K + (output_tokens / 1000) * GEMINI_OUTPUT_COST_PER_1K
    return round(cost_usd, 6), round(cost_usd * USD_TO_INR, 4)


def word_count(narrative):
    parts = [narrative.get("summary", ""), narrative.get("career_guidance", ""), narrative.get("overall_insight", "")]
    parts += narrative.get("strengths", []) + narrative.get("improvements", []) + narrative.get("recommendations", [])
    return sum(len(str(p).split()) for p in parts)


def run_provider(provider_name, call_fn, cost_fn):
    students = json.load(open(STUDENTS_PATH))["students"]
    provider_dir = os.path.join(OUT_DIR, provider_name)
    os.makedirs(provider_dir, exist_ok=True)

    for student in students:
        prompt = build_prompt(student)
        start = time.time()
        narrative, in_tok, out_tok, status, error = None, 0, 0, "error", None
        try:
            narrative, in_tok, out_tok = call_fn(prompt, SYSTEM_PROMPT)
            status = "success"
        except Exception as e:
            error = str(e)
        elapsed = round(time.time() - start, 2)

        pdf_path = pdf_size = None
        if narrative:
            fname = f"{student['id']}_{student['name'].replace(' ', '_')}.pdf"
            pdf_path = os.path.join(provider_dir, fname)
            try:
                generate_pdf(student, narrative, pdf_path)
                pdf_size = os.path.getsize(pdf_path)
            except Exception as e:
                status, error = "pdf_error", str(e)

        cost_usd, cost_inr = cost_fn(in_tok, out_tok)
        row = {
            "provider": provider_name,
            "student_id": student["id"],
            "student_name": student["name"],
            "status": status,
            "error": error,
            "time_seconds": elapsed,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "total_tokens": in_tok + out_tok,
            "cost_usd": cost_usd,
            "cost_inr": cost_inr,
            "word_count": word_count(narrative) if narrative else 0,
            "pdf_path": pdf_path,
            "pdf_size_bytes": pdf_size,
            "narrative": narrative,
        }
        with results_lock:
            results.append(row)
        print(f"[{provider_name}] {student['id']} {student['name']}: {status} in {elapsed}s, tokens={in_tok + out_tok}", flush=True)


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    hermes_call = functools.partial(llm_client.call_llm, provider="hermes")
    hermes_cost = functools.partial(llm_client.calculate_cost, provider="hermes")

    t_gemini = threading.Thread(target=run_provider, args=("gemini", call_gemini, gemini_cost))
    t_hermes = threading.Thread(target=run_provider, args=("hermes", hermes_call, hermes_cost))

    overall_start = time.time()
    t_gemini.start()
    t_hermes.start()
    t_gemini.join()
    t_hermes.join()
    overall_elapsed = round(time.time() - overall_start, 2)

    with open(os.path.join(OUT_DIR, "results.json"), "w") as f:
        json.dump({"overall_elapsed_seconds": overall_elapsed, "results": results}, f, indent=2)

    print(f"DONE in {overall_elapsed}s total")
