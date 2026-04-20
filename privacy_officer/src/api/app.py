import os
import re
import json
import asyncio
import difflib
from collections import Counter
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import pandas as pd
import shutil
from pathlib import Path

# Important: we import our core offline Privacy Agent
from src.core.privacy_agent import process_dataframe_async

app = FastAPI(title="Fontys Privacy Officer Agent")

# Define our working directories
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
STATIC_DIR = Path("src/api/static")

# Global state for simple progress tracking (in memory, single user only for now)
progress_state = {"percentage": 0, "status": "Idle"}

STATIC_DIR = Path("src/api/static")

# Mount standard HTML/JS files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open(STATIC_DIR / "index.html", "r", encoding="utf-8") as f:
        return f.read()

def _read_csv_robust(path) -> pd.DataFrame:
    """Try common encodings × delimiters until a multi-column parse succeeds."""
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        for sep in (",", ";", "\t"):
            try:
                df = pd.read_csv(path, encoding=encoding, sep=sep)
                if len(df.columns) > 1:
                    return df
            except Exception:
                continue
    # Last resort: single-column file or truly unreadable
    raise HTTPException(
        status_code=400,
        detail="Could not parse the CSV file. Make sure it uses comma, semicolon, or tab as separator and is saved as UTF-8 or Latin-1."
    )


_TAG_PATTERN = re.compile(r'\[(?:NAME|TITLE|PII|LOCATION|COURSE[/_]?DEPT|PHYSICAL_DESCRIPTOR|STUDENT_NR|EMAIL|PHONE)[^\]]*\]')


def _find_extra_replacements(original: str, anonymized: str, expected_values: list) -> list:
    """
    Returns a list of words that were unexpectedly replaced by a [TAG].
    Uses word-level difflib to find replaced segments, then checks each word
    individually against the expected PII values.
    """
    if not isinstance(original, str) or not isinstance(anonymized, str):
        return []
    if not original.strip() or anonymized.startswith('[NEEDS_REVIEW'):
        return []
    expected_lower = [v.lower() for v in expected_values if v]
    orig_words = original.split()
    anon_words = anonymized.split()
    extra = []
    matcher = difflib.SequenceMatcher(None, orig_words, anon_words, autojunk=False)
    for opcode, i1, i2, j1, j2 in matcher.get_opcodes():
        if opcode != 'replace':
            continue
        anon_segment = ' '.join(anon_words[j1:j2])
        if not _TAG_PATTERN.search(anon_segment):
            continue
        # Check each word in the replaced segment individually
        for word in orig_words[i1:i2]:
            clean = word.lower().strip('.,!?;:()"\'')
            if len(clean) <= 2:
                continue
            was_expected = any(
                exp in clean or clean in exp
                for exp in expected_lower
            )
            if not was_expected:
                extra.append(word)
    return extra


def _run_recall_check(df: pd.DataFrame, anon_col: str, pii_col: str) -> dict:
    """
    Check whether PII values listed in pii_col are absent from anon_col.
    Also detects unexpected replacements (false positives) via word-level diff.
    Returns a dict with recall + false-positive stats ready to include in the API response.
    pii_col format per cell: "naam:Smith, email:j.smith@fontys.nl"
    """
    results, missed_per_row, extras_per_row = [], [], []

    # Derive original text column from the anonymized column name (strip "anonymized_" prefix)
    orig_col = anon_col[len("anonymized_"):] if anon_col.startswith("anonymized_") else None
    if orig_col not in df.columns:
        orig_col = None

    for _, row in df.iterrows():
        anon_text = str(row.get(anon_col, ""))
        pii_label = str(row.get(pii_col, ""))
        missed = []
        expected = []
        for pair in pii_label.split(","):
            pair = pair.strip()
            if ":" not in pair:
                continue
            _, value = pair.split(":", 1)
            value = value.strip()
            if value:
                expected.append(value)
                if value.lower() in anon_text.lower():
                    missed.append(value)
        results.append(len(missed) == 0)
        missed_per_row.append(", ".join(missed))

        orig_text = str(row.get(orig_col, "")) if orig_col else ""
        extras = _find_extra_replacements(orig_text, anon_text, expected)
        extras_per_row.append(", ".join(extras))

    df["geanonimiseerd"]     = results
    df["gemiste_pii"]        = missed_per_row
    df["extra_geanonimiseerd"] = extras_per_row

    total         = len(df)
    fully_anon    = sum(results)
    recall        = round(fully_anon / total * 100, 1) if total else 0
    extra_count   = sum(1 for e in extras_per_row if e)

    # Per-theme breakdown (first column assumed to be theme)
    theme_col = df.columns[0]
    per_theme = []
    for theme, grp in df.groupby(theme_col):
        ok = int(grp["geanonimiseerd"].sum())
        fp = int((grp["extra_geanonimiseerd"].astype(str).str.len() > 0).sum())
        per_theme.append({"theme": str(theme), "score": ok, "total": len(grp), "false_positives": fp})

    # Top missed values
    all_missed = [v for row in missed_per_row for v in row.split(", ") if v]
    top_missed = [{"value": v, "count": c} for v, c in Counter(all_missed).most_common()]

    # Top unexpected replacements
    all_extras = [v for row in extras_per_row for v in row.split(", ") if v]
    top_extras = [{"value": v, "count": c} for v, c in Counter(all_extras).most_common()]

    return {
        "recall":           recall,
        "total":            total,
        "fully_anonymized": fully_anon,
        "missed_count":     total - fully_anon,
        "extra_count":      extra_count,
        "per_theme":        per_theme,
        "top_missed":       top_missed,
        "top_extras":       top_extras,
    }


@app.post("/api/anonymize")
async def anonymize_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), 
    text_column: str = Form("feedback_text"),
    anon_names: bool = Form(True),
    anon_locations: bool = Form(True),
    anon_pii: bool = Form(True),
    anon_titles: bool = Form(True),
    anon_physical: bool = Form(True),
    anon_courses: bool = Form(True),
    anon_student_nr: bool = Form(True),
    anon_floors: bool = Form(True),
    anon_bsn: bool = Form(True),
    anon_postcode: bool = Form(True),
    layers: List[str] = Form(default=[]),
    run_check: bool = Form(False),
    pii_reference_column: str = Form("voorkomende tekst van pii of indirect wat eruit gehaald moet worden"),
):
    """
    Takes an uploaded CSV, runs it through the local Ollama Privacy Agent, 
    and returns the safe/scrubbed file.
    """
    input_path = UPLOAD_DIR / f"raw_{file.filename}"
    output_path = UPLOAD_DIR / f"safe_{file.filename}"

    # 1. Save uploaded file
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 2. Process using our offline AI logic
    df = _read_csv_robust(input_path)
    
    if text_column not in df.columns:
        raise HTTPException(status_code=400, detail=f"Column '{text_column}' not found in the CSV. Available columns: {list(df.columns)}")
    
    # Reset progress
    global progress_state
    progress_state["percentage"] = 0
    progress_state["status"] = "Processing started..."
    
    # Helper to parse string form values to booleans (since JS sends "true"/"false")
    def parse_bool(val):
        return str(val).lower() == 'true'

    # Normalize layers: empty list = all layers (None); otherwise validate and pass set
    VALID_LAYERS = {"1", "2", "3"}
    if not layers:
        layers_set = None  # all layers
    else:
        layers_set = set(str(l).strip() for l in layers if l)
        invalid = layers_set - VALID_LAYERS
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid layer(s): {sorted(invalid)}. Valid: 1, 2, 3."
            )

    config = {
        "names": parse_bool(anon_names),
        "locations": parse_bool(anon_locations),
        "pii": parse_bool(anon_pii),
        "titles": parse_bool(anon_titles),
        "physical": parse_bool(anon_physical),
        "courses": parse_bool(anon_courses),
        "student_nr": parse_bool(anon_student_nr),
        "floors": parse_bool(anon_floors),
        "bsn": parse_bool(anon_bsn),
        "postcode": parse_bool(anon_postcode),
    }
    
    # Pick model name from env based on active backend
    backend = os.getenv('LLM_BACKEND', 'vllm')
    if backend == 'vllm':
        model_name = os.getenv('VLLM_MODEL', 'microsoft/Phi-3-mini-4k-instruct')
    else:
        model_name = os.getenv('OLLAMA_MODEL', 'aya-expanse:8b')
    
    # We pass progress_state to process_dataframe_async so it can update it in real-time
    processed_df = await process_dataframe_async(df, text_column=text_column, model_name=model_name, config=config, progress_state=progress_state, layers=layers_set)
    
    # 3. Recall check (optional)
    check_result = None
    anon_col = f"anonymized_{text_column}"
    if run_check:
        if pii_reference_column in processed_df.columns:
            check_result = _run_recall_check(processed_df, anon_col, pii_reference_column)
        else:
            check_result = {"error": f"Column '{pii_reference_column}' not found in CSV — check skipped."}

    # 4. Export to a new CSV file
    processed_df.to_csv(output_path, index=False)

    # Count flagged items
    flagged_series = processed_df[anon_col].astype(str).str.startswith('[NEEDS_REVIEW_')
    flagged_count = int(flagged_series.sum())

    progress_state["percentage"] = 100
    progress_state["status"] = "Complete"

    return {
        "message":      "Success",
        "download_url": f"/api/download/safe_{file.filename}",
        "flagged_count": flagged_count,
        "check":        check_result,
    }

@app.get("/api/progress")
async def get_progress(request: Request):
    """Server-Sent Events endpoint to push progress updates to the client."""
    async def event_generator():
        while True:
            # If client disconnects, stop sending events
            if await request.is_disconnected():
                break
                
            yield f"data: {json.dumps(progress_state)}\n\n"
            
            if progress_state["percentage"] >= 100:
                break
                
            await asyncio.sleep(0.5) # Send update every 0.5 seconds
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    file_path = UPLOAD_DIR / filename
    return FileResponse(path=file_path, filename=filename, media_type='text/csv')
