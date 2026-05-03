# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A multi-agent monorepo for Fontys (Dutch university). Currently contains one agent: the **Privacy Officer**, which anonymizes student feedback data using a **triple-layer** approach (Microsoft Presidio + EU-PII-Safeguard transformer + local Ollama LLM). All processing is 100% offline — data never leaves the local system.

## Running the Privacy Officer

Everything runs via Docker Compose from within `privacy_officer/`:

```bash
cd privacy_officer
docker-compose up --build
```

- Web UI: http://localhost:8000
- Ollama API: http://localhost:11435 (mapped from 11434 internally)
- On first run, `aya-expanse:8b` (~5GB) is pulled automatically — this takes several minutes.
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
├── src/core/data_loader.py     # CSV + Parquet loading
├── src/core/data_exporter.py   # CSV / Parquet / JSONL export
├── main.py                 # CLI entry point
└── scripts/
    ├── ollama_entrypoint.sh    # Docker: starts Ollama + pulls model
    └── create_dummy_data.py    # Generates test CSV (student_feedback.csv)
```

### Triple-Layer Anonymization Pipeline (`src/core/privacy_agent.py`)

1. **Layer 1 – Presidio**: Deterministic NER + regex. Detects PERSON, EMAIL_ADDRESS, PHONE_NUMBER, LOCATION, STUDENT_NUMBER (5–7 digit custom recognizer), NRP. Auto-detects Dutch/English; falls back to Dutch. Replaces with `[NAME]`, `[LOCATION]`, `[PII]`, etc.

2. **Layer 2 – EU-PII-Safeguard**: Transformer model (`tabularisai/eu-pii-safeguard`). Catches named entities Presidio missed (complex formatting, spelling variations). Runs in-process via Hugging Face transformers.

3. **Layer 3 – Ollama LLM** (inside `anonymize_text()`): Sends Layer-2 output with a JSON extraction prompt via `get_dynamic_prompt()`. Identifies contextual PII (names, titles, locations, courses, physical descriptors). Categories toggled by user config. Sorts extracted entities by length descending before replacement.

4. **Layer selection**: Users can enable/disable layers via checkboxes in the UI. Empty selection = all layers. Passed as `layers` parameter to `process_dataframe` and `anonymize_text`.

5. **Safety checks**: On JSON parse failure or LLM exception, appends `[NEEDS_REVIEW_ERROR]` and returns the original text for human review.

### Web API (`src/api/app.py`)

- `POST /api/anonymize` — accepts multipart form: CSV or Parquet file + `text_column` + layer checkboxes (1–3) + boolean flags per PII category. Runs anonymization **synchronously**; progress tracked in a global in-memory dict (single-user only).
- `GET /api/progress` — Server-Sent Events stream polling `progress_state` every 0.5s.
- `GET /api/download/{filename}` — download the anonymized file (CSV / Parquet / JSONL) from `uploads/`.
- `POST /api/detect-columns` — reads headers from an uploaded CSV or Parquet file without loading the full dataset; used by the UI to auto-detect the text column on upload.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LLM_BACKEND` | `vllm` | Layer 3 backend: `ollama` or `vllm` |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama service URL |
| `OLLAMA_MODEL` | `aya-expanse:8b` | Ollama model to use |
| `OLLAMA_TIMEOUT_SECONDS` | `600` | Timeout for Ollama requests (small GPUs need more) |
| `VLLM_HOST` | `http://vllm:8000` | vLLM service URL |
| `VLLM_MODEL` | `Qwen/Qwen2.5-3B-Instruct-AWQ` | vLLM model to use |
| `PIPELINE_BATCH_SIZE` | `512` | Rows processed per batch |
| `LAYER2_FP16` | `0` | Set to `1` to run EU-PII-Safeguard in FP16 (faster, needs GPU) |
| `HF_TOKEN` | — | Optional Hugging Face token for model downloads |
| `INPUT_FILE` | `data/input.csv` | CLI: input file path (CSV or Parquet) |
| `OUTPUT_FILE` | `data/output.csv` | CLI: output CSV path |
| `TEXT_COLUMN` | `feedback_text` | Column to anonymize |

## Key Constraints

- The `uploads/` directory (processed files) and all `*.csv` files are gitignored.
- The `venv/` directory is gitignored — always use the Docker workflow for reproducibility.
- GPU support is configured in `docker-compose.yml` via NVIDIA device reservation; remove that block if no GPU is available.
- Model pull happens at container start via `scripts/ollama_entrypoint.sh`; changing the model requires updating both this script and the `OLLAMA_MODEL` env var.
