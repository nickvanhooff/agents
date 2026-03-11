import os
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import pandas as pd
import shutil
from pathlib import Path

# Important: we import our core offline Privacy Agent
from src.core.privacy_agent import process_dataframe

app = FastAPI(title="Fontys Privacy Officer Agent")

# Define our working directories
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
STATIC_DIR = Path("src/api/static")

# Mount standard HTML/JS files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open(STATIC_DIR / "index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/anonymize")
async def anonymize_csv(file: UploadFile = File(...), text_column: str = Form("feedback_text")):
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
    df = pd.read_csv(input_path)
    
    if text_column not in df.columns:
        raise HTTPException(status_code=400, detail=f"Column '{text_column}' not found in the CSV. Available columns: {list(df.columns)}")
    
    # Using our default local model standard
    model_name = os.getenv('OLLAMA_MODEL', 'llama3.2:latest')
    
    processed_df = process_dataframe(df, text_column=text_column, model_name=model_name)
    
    # 3. Export to a new CSV file
    processed_df.to_csv(output_path, index=False)

    return {"message": "Success", "download_url": f"/api/download/safe_{file.filename}"}

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    file_path = UPLOAD_DIR / filename
    return FileResponse(path=file_path, filename=filename, media_type='text/csv')
