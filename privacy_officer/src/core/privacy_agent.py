import os
import ollama
import pandas as pd
from tqdm import tqdm
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Read OLLAMA_HOST from env so it works both locally and in Docker.
# Locally: defaults to http://localhost:11434
# Docker:  docker-compose sets OLLAMA_HOST=http://host.docker.internal:11434
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
client = ollama.Client(host=OLLAMA_HOST)
logging.info(f"Connecting to Ollama at: {OLLAMA_HOST}")

SYSTEM_PROMPT = """You are a strict text anonymization tool for an educational organization.
Your ONLY job is to find and replace privacy-sensitive words or phrases with placeholder tags.
The input text can be in Dutch or English. You MUST NOT translate the text.

=== WHAT TO REPLACE ===
Replace ONLY these specific entities, using EXACTLY these tags:
1. Personal names (students, teachers, staff) -> [NAME]
2. Honorifics/titles directly before a name (Meneer, Mevrouw, Dr., Prof.) -> [TITLE]
3. Specific named locations: cities, campuses, street names -> [LOCATION]
4. Specific named courses or department names -> [COURSE/DEPT]
5. Email addresses, student/employee numbers, phone numbers -> [PII]
6. Physical appearance details that could identify a specific person:
   - Specific body features (e.g., kaal, baard, bril)
   - Specific clothing items (e.g., wit overhemd, rode jas, blauwe pet)
   - Identifying physical states (e.g., zweterig/sweaty, hinkt)
   -> [PHYSICAL_DESCRIPTOR]

=== WHAT NOT TO REPLACE ===
Do NOT tag these — they are generic words, not identifying information:
- Generic nouns: workshop, library, bibliotheek, kantine, klas, lokaal, stage, afstudeerstage, campus (when used generically), gebouw
- Body parts: voeten, handen, hoofd, armen, benen
- Roles/functions without a name: "de docent", "mijn mentor", "my supervisor" (only tag the NAME that follows, not the role itself)
- Emotions or actions: boos, schreeuwde, blij

=== STRICT RULES ===
- PRESERVE the original sentence structure word-for-word. Replace ONLY the identifying words.
- Do NOT rewrite, paraphrase, summarize, or restructure any sentence.
- Do NOT invent new tags. Use ONLY: [NAME], [TITLE], [LOCATION], [COURSE/DEPT], [PII], [PHYSICAL_DESCRIPTOR]
- Do NOT add [PII] or any tag if there is nothing to anonymize in that spot.
- Return the result as a SINGLE LINE. Never add line breaks or newlines.
- Return ONLY the anonymized text. No explanations, no introductions.

=== EXAMPLES ===
Input:  De docent Jan Janssen in Eindhoven gaf geweldige lessen.
Output: De docent [NAME] in [LOCATION] gaf geweldige lessen.

Input:  I really enjoyed the specific workshop given by Sarah Smith at the Amsterdam campus.
Output: I really enjoyed the specific workshop given by [NAME] at the [LOCATION] campus.

Input:  the teacher who is bald and with a white shirt on and sweaty was really mad.
Output: the teacher who is [PHYSICAL_DESCRIPTOR] and with a [PHYSICAL_DESCRIPTOR] on and [PHYSICAL_DESCRIPTOR] was really mad.

Input:  De faciliteiten in het gebouw in Den Haag kunnen veel beter, vooral in de kantine van mevrouw Bakker.
Output: De faciliteiten in het gebouw in [LOCATION] kunnen veel beter, vooral in de kantine van [TITLE] [NAME].
"""

def anonymize_text(text: str, model_name: str = 'llama3.2:latest') -> str:
    """
    Uses a local Ollama model (default: llama3.2:latest) to anonymize names, 
    locations, and educational privacy markers in the given text.
    """
    if pd.isna(text) or not str(text).strip():
        return text

    try:
        response = client.chat(
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
