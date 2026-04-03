import os
import json
import asyncio
from typing import List
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
    layers: List[str] = Form(default=[])
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
    try:
        df = pd.read_csv(input_path)
    except UnicodeDecodeError:
        # Fallback to Latin-1 if UTF-8 fails (common for files with special characters like ë)
        df = pd.read_csv(input_path, encoding='latin-1')
    
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
        "student_nr": parse_bool(anon_student_nr)
    }
    
    # Pick model name from env based on active backend
    backend = os.getenv('LLM_BACKEND', 'vllm')
    if backend == 'vllm':
        model_name = os.getenv('VLLM_MODEL', 'microsoft/Phi-3-mini-4k-instruct')
    else:
        model_name = os.getenv('OLLAMA_MODEL', 'aya-expanse:8b')
    
    # We pass progress_state to process_dataframe_async so it can update it in real-time
    processed_df = await process_dataframe_async(df, text_column=text_column, model_name=model_name, config=config, progress_state=progress_state, layers=layers_set)
    
    # 3. Export to a new CSV file
    processed_df.to_csv(output_path, index=False)
    
    # Count flagged items
    flagged_series = processed_df[f'anonymized_{text_column}'].astype(str).str.startswith('[NEEDS_REVIEW_')
    flagged_count = int(flagged_series.sum())
    
    progress_state["percentage"] = 100
    progress_state["status"] = "Complete"

    return {"message": "Success", "download_url": f"/api/download/safe_{file.filename}", "flagged_count": flagged_count}

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
