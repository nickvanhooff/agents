import os
import ollama
import pandas as pd
from tqdm import tqdm
import logging
import time
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Read OLLAMA_HOST from env so it works both locally and in Docker.
# Locally: defaults to http://localhost:11434
# Docker:  docker-compose sets OLLAMA_HOST=http://host.docker.internal:11434
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
client = ollama.Client(host=OLLAMA_HOST)
logging.info(f"Connecting to Ollama at: {OLLAMA_HOST}")

# Initialize Presidio multi-language NLP engine
logging.info("Initializing Microsoft Presidio NLP engines (this may take a moment)...")
provider = NlpEngineProvider(nlp_configuration={
    "nlp_engine_name": "spacy",
    "models": [
        {"lang_code": "nl", "model_name": "nl_core_news_lg"},
        {"lang_code": "en", "model_name": "en_core_web_lg"},
    ]
})
nlp_engine = provider.create_engine()
analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["nl", "en"])

# Add Custom Recognizer for Student Numbers (5 to 7 digits)
student_pattern = Pattern(name="student_number_pattern", regex=r'\b[0-9]{5,7}\b', score=0.85)
student_recognizer_nl = PatternRecognizer(supported_entity="STUDENT_NUMBER", patterns=[student_pattern], supported_language="nl")
student_recognizer_en = PatternRecognizer(supported_entity="STUDENT_NUMBER", patterns=[student_pattern], supported_language="en")
analyzer.registry.add_recognizer(student_recognizer_nl)
analyzer.registry.add_recognizer(student_recognizer_en)

anonymizer = AnonymizerEngine()

PRESIDIO_OPERATORS = {
    "PERSON":        OperatorConfig("replace", {"new_value": "[NAME]"}),
    "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[PII]"}),
    "PHONE_NUMBER":  OperatorConfig("replace", {"new_value": "[PII]"}),
    "STUDENT_NUMBER":OperatorConfig("replace", {"new_value": "[PII]"}),
    "LOCATION":      OperatorConfig("replace", {"new_value": "[LOCATION]"}),
    "NRP":           OperatorConfig("replace", {"new_value": "[NAME]"}), # Nationality/Religious/Political sometimes catches groups/names
    "DEFAULT":       OperatorConfig("keep"), # We ignore other things that Presidio finds
}

def presidio_anonymize(text: str, config: dict = None) -> str:
    """Uses Microsoft Presidio NER to securely extract structured PII before sending context to LLM."""
    if not text.strip(): return text
    
    # Try to detect language, default to Dutch since data is mostly Dutch
    try:
        lang = detect(text)
        if lang not in ["nl", "en"]:
            lang = "nl"
    except LangDetectException:
        lang = "nl"
        
    # Dynamically build operators based on config
    operators = {}
    if config:
        operators["PERSON"] = OperatorConfig("replace", {"new_value": "[NAME]"}) if config.get("names", True) else OperatorConfig("keep")
        operators["NRP"] = OperatorConfig("replace", {"new_value": "[NAME]"}) if config.get("names", True) else OperatorConfig("keep")
        operators["LOCATION"] = OperatorConfig("replace", {"new_value": "[LOCATION]"}) if config.get("locations", True) else OperatorConfig("keep")
        operators["EMAIL_ADDRESS"] = OperatorConfig("replace", {"new_value": "[PII]"}) if config.get("pii", True) else OperatorConfig("keep")
        operators["PHONE_NUMBER"] = OperatorConfig("replace", {"new_value": "[PII]"}) if config.get("pii", True) else OperatorConfig("keep")
        operators["STUDENT_NUMBER"] = OperatorConfig("replace", {"new_value": "[PII]"}) if config.get("student_nr", True) else OperatorConfig("keep")
    else:
        operators = PRESIDIO_OPERATORS
        
    operators["DEFAULT"] = OperatorConfig("keep")
        
    results = analyzer.analyze(text=text, language=lang)
    result = anonymizer.anonymize(text=text, analyzer_results=results, operators=operators)
    return result.text

def get_dynamic_prompt(config: dict = None) -> str:
    """Builds a strict JSON extraction prompt based on user settings."""
    prompt = """You are a strict data extraction tool. Your ONLY job is to extract identifying entities from the text.
You MUST output ONLY a valid JSON object. Do not output anything else.
The JSON object must contain arrays of exact strings found in the text that match the requested categories.
If no matches are found for a category, return an empty array [] for that key.

=== CATEGORIES TO EXTRACT ===\n"""

    if not config or config.get("names", True):
        prompt += "- 'names': Personal names (students, teachers, staff)\n"
    if not config or config.get("titles", True):
        prompt += "- 'titles': Honorifics or titles directly before a name (e.g., Meneer, Mevrouw, Dr., docent, mentor)\n"
    if not config or config.get("locations", True):
        prompt += "- 'locations': Specific locations (cities, campuses, street names)\n"
    if not config or config.get("courses", True):
        prompt += "- 'courses': Specific named courses or department names\n"
    if not config or config.get("pii", True) or config.get("student_nr", True):
        prompt += "- 'pii': Email addresses, student numbers, employee numbers, phone numbers\n"
    if not config or config.get("physical", True):
        prompt += "- 'physical': Physical appearance details identifying a person (e.g., kaal, baard, rode jas)\n"

    prompt += """
=== STRICT RULES ===
1. The strings in your JSON arrays MUST be EXACT substrings from the input text. Do not correct spelling or alter capitalization.
2. DO NOT extract generic words (like 'workshop', 'bibliotheek', 'kantine', 'eten', 'voeten', 'blij'). 
3. DO NOT extract standalone numbers or grades (like '1', '4', '8.5').
4. The output must be parsable by Python's json.loads().
"""
    return prompt

def anonymize_text(text: str, model_name: str = 'llama3.2:latest', config: dict = None) -> str:
    """Anonymize a single text string using Presidio and local LLM."""
    if not isinstance(text, str) or not text.strip():
        return text

    # Step 1: Microsoft Presidio (Deterministic Regex/NER)
    try:
        # Try to detect language, default to Dutch since data is mostly Dutch
        try:
            lang = detect(text)
            if lang not in ["nl", "en"]:
                lang = "nl"
        except LangDetectException:
            lang = "nl"

        results = analyzer.analyze(text=text, language=lang)
        
        # Build operators based on config
        operators = {}
        if config:
            operators["PERSON"] = OperatorConfig("replace", {"new_value": "[NAME]"}) if config.get("names", True) else OperatorConfig("keep")
            operators["NRP"] = OperatorConfig("replace", {"new_value": "[NAME]"}) if config.get("names", True) else OperatorConfig("keep") # Added NRP back based on original presidio_anonymize
            operators["LOCATION"] = OperatorConfig("replace", {"new_value": "[LOCATION]"}) if config.get("locations", True) else OperatorConfig("keep")
            operators["EMAIL_ADDRESS"] = OperatorConfig("replace", {"new_value": "[PII]"}) if config.get("pii", True) else OperatorConfig("keep")
            operators["PHONE_NUMBER"] = OperatorConfig("replace", {"new_value": "[PII]"}) if config.get("pii", True) else OperatorConfig("keep")
            operators["STUDENT_NUMBER"] = OperatorConfig("replace", {"new_value": "[PII]"}) if config.get("pii", True) else OperatorConfig("keep") # Changed from student_nr to pii based on original presidio_anonymize
        else:
            operators = PRESIDIO_OPERATORS
        
        operators["DEFAULT"] = OperatorConfig("keep") # Added back based on original presidio_anonymize
            
        anonymized_result = anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators
        )
        presidio_anonymized = anonymized_result.text
        
        if results:
            logging.info(f"Presidio matched {len(results)} entities -> Output: '{presidio_anonymized}'")
            
    except Exception as e:
        logging.error(f"Presidio error on '{text[:30]}...': {e}")
        presidio_anonymized = text

    # If everything is turned off, just return original text
    if config and not any(config.values()):
        return text

    try:
        prompt_str = get_dynamic_prompt(config)
        import json
        import re
        
        response = client.chat(model=model_name, messages=[
            {"role": "system", "content": prompt_str},
            {"role": "user", "content": presidio_anonymized}
        ], format="json")
        
        # safely parse the json response
        try:
            extracted_entities = json.loads(response['message']['content'].strip())
        except json.JSONDecodeError:
            logging.error(f"Failed to parse JSON for input: {text[:30]}")
            return f"[NEEDS_REVIEW_ERROR] {text}"
            
        anonymized = presidio_anonymized
        
        # We sort by length descending to replace larger phrases before smaller overlaps
        tag_map = {
            "names": "[NAME]",
            "titles": "[TITLE]",
            "locations": "[LOCATION]",
            "courses": "[COURSE/DEPT]",
            "pii": "[PII]",
            "physical": "[PHYSICAL_DESCRIPTOR]"
        }
        
        for category, entities in extracted_entities.items():
            if isinstance(entities, list) and category in tag_map:
                tag = tag_map[category]
                # Sort descending length so "John Doe" replaces before "John"
                entities.sort(key=len, reverse=True)
                for entity in entities:
                    if isinstance(entity, str) and entity and entity in anonymized:
                        # Case insensitive replacement via regex but preserving case of other words
                        pattern = re.compile(re.escape(entity), re.IGNORECASE)
                        anonymized = pattern.sub(tag, anonymized)
                        
        return anonymized

    except Exception as e:
        logging.error(f"LLM error on '{text[:30]}...': {e}")
        return f"[NEEDS_REVIEW_ERROR] {text}"

def process_dataframe(df: pd.DataFrame, text_column: str, model_name: str = 'llama3.2:latest', config: dict = None, progress_state: dict = None) -> pd.DataFrame:
    """
    Processes a Pandas DataFrame, applying the anonymization function to the specified text column
    with a progress bar. Safe to run locally with no cloud connections.
    """
    logging.info(f"Starting anonymization process using model: {model_name}. Total rows: {len(df)}")
    
    # Create a copy to avoid SettingWithCopyWarning, though we are returning a new df anyway.
    processed_df = df.copy()
    
    # Initialize a list to hold the results
    anonymized_texts = []
    
    total_rows = len(processed_df)
    
    # Iterate with tqdm for a progress bar
    for i, text in enumerate(tqdm(processed_df[text_column], desc="Anonymizing feedback")):
        anonymized_texts.append(anonymize_text(text, model_name, config))
        
        if progress_state is not None:
            progress_state["percentage"] = int(((i + 1) / total_rows) * 100)
            progress_state["status"] = f"Processing item {i + 1} of {total_rows}..."
            
        # Small delay to prevent overwhelming the local service if necessary,
        # usually Ollama handles queuing ok, but a tiny sleep can sometimes help stability.
        time.sleep(0.01) 
        
    processed_df[f'anonymized_{text_column}'] = anonymized_texts
    
    if progress_state is not None:
        progress_state["percentage"] = 100
        progress_state["status"] = "Completed!"
    
    logging.info("Anonymization process completed.")
    return processed_df
