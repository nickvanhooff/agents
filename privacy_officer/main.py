import logging
from src.core.data_loader import load_data
from src.core.privacy_agent import process_dataframe
from src.core.data_exporter import export_data

# Configure root logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

import os

def main():
    # Configuration
    INPUT_FILE = os.getenv('INPUT_FILE', 'student_feedback.csv')
    OUTPUT_FILE = os.getenv('OUTPUT_FILE', 'anonymized_feedback.csv')
    TEXT_COLUMN_TO_ANONYMIZE = os.getenv('TEXT_COLUMN', 'feedback_text')
    
    # Configure which model Ollama uses locally. Default is 'llama3.2:latest' which is free and efficient for this task.
    MODEL_NAME = os.getenv('OLLAMA_MODEL', 'llama3.2:latest') 

    logger.info("Initializing Privacy Officer AI Agent Workflow...")

    try:
        # Step 1: Ingestion
        logger.info("STEP 1: Loading Data")
        df = load_data(INPUT_FILE)
        
        # Check if column exists
        if TEXT_COLUMN_TO_ANONYMIZE not in df.columns:
             raise ValueError(f"Required column '{TEXT_COLUMN_TO_ANONYMIZE}' not found in the dataset.")

        # Step 2: Processing (Agent Logic)
        logger.info("STEP 2: Anonymizing Data")
        processed_df = process_dataframe(df, text_column=TEXT_COLUMN_TO_ANONYMIZE, model_name=MODEL_NAME)

        # Step 3: Export
        logger.info("STEP 3: Exporting Data")
        export_data(processed_df, OUTPUT_FILE)

        logger.info("Privacy Officer AI Agent Workflow completed successfully!")

    except Exception as e:
        logger.error(f"Workflow failed: {e}")

if __name__ == "__main__":
    main()
