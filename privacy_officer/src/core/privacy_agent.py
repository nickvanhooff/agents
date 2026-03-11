import ollama
import pandas as pd
from tqdm import tqdm
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SYSTEM_PROMPT = """You are a highly strict AI Privacy Officer for an educational organization.
Your ONLY job is to redact sensitive privacy-related information from the input text. 
The input text can be in Dutch or English. You MUST NOT translate the text.

You MUST replace the following entities with their respective tags:
1. Names of ANY people (students, teachers, professors, staff) -> [NAME]
2. Titles or pronouns accompanying a name (e.g., Meneer, Mevrouw, Dr., Prof., mentor, docent) -> [TITLE]
3. Specific locations (cities, campuses, street names, buildings) -> [LOCATION]
4. School organizations, departments, or specific course/module names -> [COURSE/DEPT]
5. Email addresses, student numbers, or phone numbers -> [PII]
6. Physical descriptions or appearance details that could identify a person, such as:
   - Body features (e.g., bald, tall, short, overweight, beard, glasses)
   - Clothing or style (e.g., white shirt, red jacket, always wears a cap)
   - Bodily states that are identifying in context (e.g., sweaty, limping)
   -> [PHYSICAL_DESCRIPTOR]

Rules:
- You must NOT alter the original context, sentiment, meaning, or language of the feedback.
- Return ONLY the anonymized text and absolutely nothing else. Do not add any conversational filler or introductions.
- When in doubt about whether something is identifying, redact it.
"""

def anonymize_text(text: str, model_name: str = 'llama3.2:latest') -> str:
    """
    Uses a local Ollama model (default: llama3.2:latest) to anonymize names, 
    locations, and educational privacy markers in the given text.
    """
    if pd.isna(text) or not str(text).strip():
        return text

    try:
        response = ollama.chat(
            model=model_name,
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': str(text)}
            ]
        )
        
        anonymized = response['message']['content'].strip()
        
        # Basic hallucination/error checks
        if not anonymized:
            logging.warning(f"Empty response from model for input: '{text[:30]}...' Flagging for review.")
            return f"[NEEDS_REVIEW_EMPTY] {text}"
            
        # Check if output is suspiciously shorter or longer than input (adjust thresholds as needed)
        input_len = len(str(text))
        output_len = len(anonymized)
        
        if output_len < (input_len * 0.2) or output_len > (input_len * 3):
             logging.warning(f"Suspicious output length for input: '{text[:30]}...' Flagging for review.")
             return f"[NEEDS_REVIEW_LENGTH] {text}"

        return anonymized

    except Exception as e:
        logging.error(f"Error during anonymization of text '{text[:30]}...': {e}")
        return f"[NEEDS_REVIEW_ERROR] {text}"

def process_dataframe(df: pd.DataFrame, text_column: str, model_name: str = 'llama3.2:latest') -> pd.DataFrame:
    """
    Processes a Pandas DataFrame, applying the anonymization function to the specified text column
    with a progress bar. Safe to run locally with no cloud connections.
    """
    logging.info(f"Starting anonymization process using model: {model_name}. Total rows: {len(df)}")
    
    # Create a copy to avoid SettingWithCopyWarning, though we are returning a new df anyway.
    processed_df = df.copy()
    
    # Initialize a list to hold the results
    anonymized_texts = []
    
    # Iterate with tqdm for a progress bar
    for text in tqdm(processed_df[text_column], desc="Anonymizing feedback"):
        anonymized_texts.append(anonymize_text(text, model_name))
        # Small delay to prevent overwhelming the local service if necessary,
        # usually Ollama handles queuing ok, but a tiny sleep can sometimes help stability.
        time.sleep(0.01) 
        
    processed_df[f'anonymized_{text_column}'] = anonymized_texts
    
    logging.info("Anonymization process completed.")
    return processed_df
