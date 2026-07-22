import os
import io
import csv
import json
import time
import zipfile

from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS

from prompt import SYSTEM_PROMPT, build_prompt, FALLBACK_NARRATIVE
from gemini_client import call_gemini_flash, estimate_tokens, calculate_cost
from pdf_generator import generate_pdf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
OUTPUT_DIR = os.path.join(ROOT_DIR, "output", "pdfs")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = Flask(__name__)
CORS(app)

STUDENTS = {}  # in-memory store: id -> student dict, populated via /upload
BATCH_DELAY_SECONDS = 1  # gentle spacing between calls so /batch stays under free-tier rate limits

KNOWN_FIELDS = {"id", "name", "class", "percentile", "attendance"}


def _safe_filename(student):
    name = student.get("name") or student.get("id") or "student"
    name = "".join(c for c in name if c.isalnum() or c in (" ", "_")).strip().replace(" ", "_")
    return f"{student.get('id', 'S000')}_{name or 'student'}.pdf"


def _parse_csv(file_stream):
    text = file_stream.read().decode("utf-8-sig")  # utf-8-sig strips a BOM if present (common in Excel exports)
    reader = csv.DictReader(io.StringIO(text))
    # Match id/name/class/percentile/attendance case-insensitively; everything else is a score subject.
    fieldnames = reader.fieldnames or []
    key_map = {f: (f.strip().lower() if f.strip().lower() in KNOWN_FIELDS else f) for f in fieldnames}

    students = []
    for i, raw_row in enumerate(reader, start=1):
        row = {key_map[k]: (v.strip() if isinstance(v, str) else v) for k, v in raw_row.items() if k}
        scores = {}
        for k, v in row.items():
            if k in KNOWN_FIELDS or v in (None, ""):
                continue
            try:
                scores[k] = int(v)
            except ValueError:
                try:
                    scores[k] = float(v)
                except ValueError:
                    pass  # non-numeric column that isn't a known field; skip rather than crash
        students.append(
            {
                "id": row.get("id") or f"S{i:03d}",
                "name": row.get("name") or f"Student {i}",
                "class": row.get("class", ""),
                "scores": scores,
                "percentile": int(row["percentile"]) if row.get("percentile") else None,
                "attendance": int(row["attendance"]) if row.get("attendance") else None,
            }
        )
    return students


def _extract_students(payload):
    if isinstance(payload, list):
        return payload
    return payload.get("students", [])


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/upload", methods=["POST"])
def upload():
    if "file" in request.files:
        f = request.files["file"]
        if f.filename.lower().endswith(".csv"):
            students = _parse_csv(f.stream)
        else:
            students = _extract_students(json.load(f.stream))
    else:
        students = _extract_students(request.get_json(force=True))

    for s in students:
        STUDENTS[s["id"]] = s

    return jsonify({"loaded": len(students), "students": students})


def _process_student(student):
    prompt = build_prompt(student)
    try:
        narrative, input_tokens, output_tokens = call_gemini_flash(prompt, SYSTEM_PROMPT)
        used_fallback = False
    except Exception:
        narrative = FALLBACK_NARRATIVE
        input_tokens = estimate_tokens(prompt)
        output_tokens = estimate_tokens(json.dumps(FALLBACK_NARRATIVE))
        used_fallback = True

    filename = _safe_filename(student)
    output_path = os.path.join(OUTPUT_DIR, filename)
    generate_pdf(student, narrative, output_path)

    cost_usd, cost_inr = calculate_cost(input_tokens, output_tokens)
    return {
        "id": student["id"],
        "name": student["name"],
        "status": "done_with_fallback" if used_fallback else "done",
        "filename": filename,
        "download_url": f"/download/{filename}",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cost_usd": cost_usd,
        "cost_inr": cost_inr,
    }


@app.route("/generate", methods=["POST"])
def generate():
    payload = request.get_json(force=True) or {}
    student = payload.get("student")
    if student is None and "id" in payload:
        student = STUDENTS.get(payload["id"])
    if student is None:
        return jsonify({"error": "student not found"}), 404

    start = time.time()
    try:
        result = _process_student(student)
    except Exception as e:
        return jsonify({"id": student.get("id"), "status": "error", "error": str(e)}), 500
    result["processing_time_seconds"] = round(time.time() - start, 2)
    return jsonify(result)


@app.route("/batch", methods=["POST"])
def batch():
    payload = request.get_json(force=True) or {}
    ids = payload.get("ids")
    students = [STUDENTS[i] for i in ids if i in STUDENTS] if ids else list(STUDENTS.values())

    start = time.time()
    results = []
    for i, student in enumerate(students):
        try:
            results.append(_process_student(student))
        except Exception as e:
            results.append({"id": student.get("id"), "name": student.get("name"), "status": "error", "error": str(e)})
        if i < len(students) - 1:
            time.sleep(BATCH_DELAY_SECONDS)

    elapsed = round(time.time() - start, 2)
    ok_results = [r for r in results if r.get("status", "").startswith("done")]
    total_input = sum(r["input_tokens"] for r in ok_results)
    total_output = sum(r["output_tokens"] for r in ok_results)
    total_cost_inr = round(sum(r["cost_inr"] for r in ok_results), 4)

    return jsonify(
        {
            "total_students": len(students),
            "succeeded": len(ok_results),
            "failed": len(results) - len(ok_results),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "estimated_cost_inr": f"₹{total_cost_inr}",
            "per_student_cost_inr": f"₹{round(total_cost_inr / len(ok_results), 4)}" if ok_results else "₹0",
            "processing_time_seconds": elapsed,
            "results": results,
        }
    )


@app.route("/download/<path:filename>", methods=["GET"])
def download(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


@app.route("/download-all", methods=["GET"])
def download_all():
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in os.listdir(OUTPUT_DIR):
            if fname.endswith(".pdf"):
                zf.write(os.path.join(OUTPUT_DIR, fname), fname)
    mem.seek(0)
    return send_file(mem, mimetype="application/zip", as_attachment=True, download_name="reports.zip")


@app.route("/", methods=["GET"])
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
