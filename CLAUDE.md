# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A multi-agent monorepo for Fontys (Dutch university). Currently contains one agent: the **Privacy Officer**, which anonymizes student feedback data using a dual-layer approach (Microsoft Presidio + local Ollama LLM). All processing is 100% offline — data never leaves the local system.

## Running the Privacy Officer

Everything runs via Docker Compose from within `privacy_officer/`:

```bash
cd privacy_officer
docker-compose up --build
```

- Web UI: http://localhost:8000
- Ollama API: http://localhost:11435 (mapped from 11434 internally)
- On first run, `llama3.1:8b` (~5GB) is pulled automatically — this takes several minutes.
- Requires Docker Desktop with 8–12GB RAM allocated.

## Development (without Docker)

```bash
cd privacy_officer
python -m venv venv
source venv/Scripts/activate   # Windows
pip install -r requirements.txt
python -m spacy download nl_core_news_lg
python -m spacy download en_core_web_lg

# Run FastAPI server (requires Ollama running separately on port 11434)
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload

# Run CLI pipeline
INPUT_FILE=input.csv TEXT_COLUMN=feedback_text python main.py
```

## Architecture

```
privacy_officer/
├── src/api/app.py          # FastAPI server: /api/anonymize, /api/progress (SSE), /api/download
├── src/api/static/         # Single-page Web UI
├── src/core/privacy_agent.py   # Core anonymization pipeline
├── src/core/data_loader.py     # CSV loading
├── src/core/data_exporter.py   # CSV export
├── main.py                 # CLI entry point
└── scripts/
    ├── ollama_entrypoint.sh    # Docker: starts Ollama + pulls model
    └── create_dummy_data.py    # Generates test CSV (student_feedback.csv)
```

### Two-Layer Anonymization Pipeline (`src/core/privacy_agent.py`)

1. **Presidio layer**: Deterministic NER + regex. Detects PERSON, EMAIL_ADDRESS, PHONE_NUMBER, LOCATION, STUDENT_NUMBER (5–7 digit custom recognizer), NRP. Auto-detects Dutch/English; falls back to Dutch. Replaces with `[NAME]`, `[LOCATION]`, `[PII]`, etc.
   - `presidio_anonymize()` — standalone utility function
   - `anonymize_text()` — the main pipeline function; it **inlines its own Presidio logic** (does not call `presidio_anonymize()`), then calls Ollama

2. **Ollama LLM layer** (inside `anonymize_text()`): Sends Presidio-anonymized text with a JSON extraction prompt via `get_dynamic_prompt()`. Identifies contextual PII (names, titles, locations, courses, physical descriptors) Presidio missed. Categories toggled by user config. Sorts extracted entities by length descending before replacement to avoid partial-match clobbering.

3. **Safety checks**: On JSON parse failure or LLM exception, appends `[NEEDS_REVIEW_ERROR]` and returns the original text for human review.

### Web API (`src/api/app.py`)

- `POST /api/anonymize` — accepts multipart form: CSV file + boolean flags per PII category + `text_column` name. Runs anonymization **synchronously** in the request handler (blocks until complete); progress tracked in a global in-memory dict (single-user only).
- `GET /api/progress` — Server-Sent Events stream polling `progress_state` every 0.5s.
- `GET /api/download/{filename}` — download the anonymized CSV from `uploads/`.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama service URL |
| `OLLAMA_MODEL` | `llama3.2:latest` (local) / `llama3.1:8b` (Docker) | LLM model to use |
| `INPUT_FILE` | `data/input.csv` | CLI: input CSV path |
| `OUTPUT_FILE` | `data/output.csv` | CLI: output CSV path |
| `TEXT_COLUMN` | `feedback_text` | Column to anonymize |

## Key Constraints

- The `uploads/` directory (processed files) and all `*.csv` files are gitignored.
- The `venv/` directory is gitignored — always use the Docker workflow for reproducibility.
- GPU support is configured in `docker-compose.yml` via NVIDIA device reservation; remove that block if no GPU is available.
- Model pull happens at container start via `scripts/ollama_entrypoint.sh`; changing the model requires updating both this script and the `OLLAMA_MODEL` env var.
