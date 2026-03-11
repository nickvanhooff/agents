# Privacy Officer AI Agent

A modular Python agent designed to locally anonymize open text responses using an offline LLM (via Ollama). Built for handling 15,000 feedback rows seamlessly in Dutch and English without sending any data to the cloud.

## Features
- **100% Local**: No cloud APIs (OpenAI, Anthropic) are used. Data never leaves your machine.
- **Bilingual**: Handles Dutch and English in the same column seamlessly.
- **Robust Error Handling**: Flags empty LLM outputs or hallucinations for manual review rather than deleting data automatically.
- **Modular Architecture**: Easy to swap the current CSV `data_loader.py` with a Power BI or Excel connector later.
- **Container Ready**: Includes a `Dockerfile` and `docker-compose.yml` for easy deployment.
- **Traceable**: Detailed logging and error checking to ensure no data is lost during the 15,000 row process.

---

## 📖 How to Use (Web Interface)

We have built a simple, clean Web Interface so you don't need to touch code or terminals after setup.

1.  **Start the Server**: See the instructions below.
2.  **Open the App**: Go to `http://localhost:8000` in your web browser.
3.  **Upload & Process**: 
    - Drag and drop your `student_feedback.csv` into the UI.
    - Click "Start Local Anonymization."
    - Wait for the progress to finish and click **Download Anonymized CSV**.
4.  **Review Flags**: Look for any rows tagged with `[NEEDS_REVIEW_ERROR]` or `[NEEDS_REVIEW_EMPTY]`. These are rare cases where the AI was unsure, and they should be checked manually.

---

## 🤖 Which Model is Used & How it Runs

This agent relies on **[Ollama](https://ollama.com/)** to run Large Language Models (LLMs) completely locally. You have two ways to run it:

1.  **Fully Containerized (Docker)**: Everything (both the agent and the Ollama model engine) runs inside Docker. This is the most "portable" way and keeps your host machine clean.
2.  **Local/Hybrid**: You run the agent script (via `venv`) on your machine, but it talks to an Ollama installation you've installed on your Windows/Mac/Linux desktop.

- **Default Model**: The agent uses `llama3.2:latest` (an efficient and free 3B parameter model). 
- **Offline/Free**: Both methods are 100% offline and cost $0.
- **Configuration**: The model name and data paths can be changed easily using environment variables, without editing the code!
  - `OLLAMA_MODEL` (default: `llama3.2:latest`)
  - `INPUT_FILE` (default: `student_feedback.csv`)
  - `OUTPUT_FILE` (default: `anonymized_feedback.csv`)

---

## 🚀 Getting Started (Without Docker)

1. **Install Ollama**: Ensure [Ollama](https://ollama.com/) is installed and running in your background tray.
2. **Download the Model**: Pull the default local model:
   ```bash
   ollama pull llama3.2
   ```
3. **Setup Virtual Environment**:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```
4. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
5. **Generate Dummy Data** (for testing):
   ```bash
   python create_dummy_data.py
   ```
### Running the Web Server
To start the Privacy Officer interface, simply run:
```bash
python -m uvicorn src.api.app:app
```
*Then open your browser to `http://localhost:8000` to use the tool!*

---

## ⚙️ Advanced Configuration (Scaling for 15,000 Rows)

Processing 15,000 lines sequentiality through an LLM can take a few hours on standard hardware. If you need more speed:

1.  **Use a Faster Model**: Run `ollama pull qwen2:0.5b` and set `OLLAMA_MODEL=qwen2:0.5b` before running.
2.  **GPU Acceleration**: Ensure Ollama is using your system's GPU (NVIDIA/AMD/Metal). This is usually handled automatically by Ollama.
3.  **Batching**: The code is designed to handle batching natively via the `process_dataframe` loop.

## Getting Started (With Docker)

1. Ensure Docker Desktop is installed.
2. Ensure Ollama is running on your host machine.
3. Run the following command:
   ```bash
   docker-compose up --build
   ```
   *(Note: The `docker-compose.yml` connects to the host machine's Ollama instance via `host.docker.internal`.)*

## Example Data Format

The application expects input data as a Pandas DataFrame with a specified text column (e.g., `feedback_text`).

**Input CSV (`student_feedback.csv`)**
```csv
student_id,feedback_text
1,"De docent Jan Janssen in Eindhoven gaf geweldige lessen, maar het lokaal was vaak koud."
2,"I really enjoyed the specific workshop given by Sarah Smith at the Amsterdam campus."
```

**Output CSV (`anonymized_feedback.csv`)**
```csv
student_id,feedback_text,anonymized_feedback_text
1,"De docent Jan Janssen in Eindhoven gaf geweldige lessen, maar het lokaal was vaak koud.","[NAME] [TITLE] in [LOCATION] gaf geweldige lessen, maar het [COURSE/DEPT]-lokaal was vaak koud."
2,"I really enjoyed the specific workshop given by Sarah Smith at the Amsterdam campus.","I really enjoyed the specific workshop given by [NAME] at the [LOCATION]."
```
