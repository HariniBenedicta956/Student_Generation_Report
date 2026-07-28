# AI-Powered Student Assessment Report Generator

A prototype that turns structured student score data into personalized, AI-narrated PDF
assessment reports using a self-hosted OpenAI-compatible LLM endpoint for the narrative and
ReportLab for deterministic PDF formatting — following the architecture in `Architecture.md` /
`Project_requirement.md`.

## Folder Structure

```
assessment-report-generator/
├── backend/
│   ├── app.py              # Flask server (endpoints + orchestration)
│   ├── prompt.py           # Prompt templates + fallback narrative
│   ├── pdf_generator.py    # ReportLab PDF layout
│   ├── llm_client.py       # OpenAI-compatible chat completions client, tokens, cost
│   ├── requirements.txt
│   ├── .env                # Your local secrets (gitignored)
│   └── .env.example
├── frontend/
│   └── index.html          # Single-page UI (CSS/JS embedded)
├── data/
│   └── students.json       # Sample data (5 students)
└── output/
    └── pdfs/                # Generated PDFs land here
```

## Setup

1. **Install dependencies**

   ```bash
   cd assessment-report-generator/backend
   pip install -r requirements.txt
   ```

2. **Configure the LLM endpoint**

   Edit `backend/.env` (already created from `.env.example`) and set:

   ```
   LLM_API_BASE_URL=http://<your-llm-server-ip>:<port>/v1/chat/completions
   LLM_API_KEY=your_key_here
   LLM_MODEL=your_model_name
   ```

   This targets any self-hosted server that implements the OpenAI-compatible
   `/v1/chat/completions` API (LM Studio, Ollama, vLLM, text-generation-webui, etc.).

3. **Run the backend**

   ```bash
   python app.py
   ```

   Flask starts on `http://localhost:5000` and also serves the frontend directly at
   `http://localhost:5000/` (it reads `frontend/index.html`). You can alternatively just
   double-click `frontend/index.html` to open it via `file://` — it talks to the same
   `http://localhost:5000` API either way.

## Usage

1. Open the UI (`http://localhost:5000/` or `frontend/index.html`).
2. Upload `data/students.json` (or any CSV with columns like `id,name,class,Mathematics,Science,...,percentile,attendance`).
3. Review the loaded student list — every student is checked by default; untick any you don't want.
4. Click **Generate Reports**. Each selected student is sent to `/generate` one at a time so
   you see live per-student progress ("Processing 2/5...") and status badges (⏳ → ✅).
5. Watch the **Stats** panel update live: total tokens, estimated cost (₹), elapsed time,
   and reports completed.
6. Download PDFs individually via each row's **Download** link, or click
   **Download All (ZIP)** to grab everything generated so far in one file.

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/upload` | POST | Store student records (JSON body `{students:[...]}` or multipart file) server-side |
| `/generate` | POST | Generate one report — body `{"id": "S001"}` |
| `/batch` | POST | Generate reports for all (or a given list of) stored students, server-side sequential loop |
| `/download/<filename>` | GET | Download a single generated PDF |
| `/download-all` | GET | Download all currently generated PDFs as a ZIP |

`/generate` is what the frontend calls in a loop to get real-time per-student progress.
`/batch` does the same work in one blocking call server-side, useful for scripting/automation
(e.g. `curl -X POST http://localhost:5000/batch -d '{}'`).

## How Cost & Tokens Are Tracked

- When the LLM response reports `usage.prompt_tokens` / `usage.completion_tokens` (standard
  OpenAI-compatible response field), that is used directly.
- If unavailable, `estimate_tokens()` falls back to a ~1.3 tokens/word heuristic.
- Cost defaults to **₹0** (`INPUT_COST_PER_1K_USD` / `OUTPUT_COST_PER_1K_USD` default to `0` in
  `.env`) since this is a self-hosted model with no per-token billing. Set non-zero rates in
  `.env` if you want to model an amortized cost (e.g. GPU/electricity).

## Error Handling

- **LLM call failure** (timeout, connection error, malformed JSON): the call is retried up to 3
  times with a short backoff (handles transient network/model-load issues during batch runs).
  If it still fails, the student's report falls back to a generic template (`FALLBACK_NARRATIVE`
  in `prompt.py`) so the PDF is still produced and the batch continues with the next student.
- **PDF generation failure**: bubbles up as an `error` status for that student only; other
  students in the batch are unaffected.
- **Latency**: this endpoint has been observed taking 40-60s per call (self-hosted, no elastic
  capacity), so `llm_client.py` uses a generous request timeout (`LLM_REQUEST_TIMEOUT_SECONDS`,
  default 120s). `/batch` still sleeps 1 second between students to avoid hammering a single
  local instance.

## Sample Data

`data/students.json` contains 5 students with varied performance (from top performer to one
needing significant support), so generated narratives are visibly personalized rather than
generic boilerplate — matching the project's success criteria.

## Notes on Production Scaling

This prototype mirrors the recommended production architecture from `Project_requirement.md`:
deterministic score/data handling stays in code, only the narrative comes from the LLM via a
compact prompt, and PDF formatting is fully deterministic (ReportLab templates, not
AI-generated). Swapping in a different model/provider later only requires changing
`llm_client.py` — the rest of the pipeline is unaffected.
