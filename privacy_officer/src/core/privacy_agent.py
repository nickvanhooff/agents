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
    """Builds the system prompt dynamically based on what the user wants to anonymize."""
    prompt = """You are a strict text anonymization tool for an educational organization.
Your ONLY job is to find and replace privacy-sensitive words or phrases with placeholder tags.
The input text can be in Dutch or English. You MUST NOT translate the text.

=== WHAT TO REPLACE ===
Replace ONLY these specific entities, using EXACTLY these tags:\n"""

    allowed_tags = []
    
    if not config or config.get("names", True):
        prompt += "1. Personal names (students, teachers, staff) -> [NAME]\n"
        allowed_tags.append("[NAME]")
    if not config or config.get("titles", True):
        prompt += "2. Honorifics/titles directly before a name (Meneer, Mevrouw, Dr., Prof.) -> [TITLE]\n"
        allowed_tags.append("[TITLE]")
    if not config or config.get("locations", True):
        prompt += "3. Specific named locations: cities, campuses, street names -> [LOCATION]\n"
        allowed_tags.append("[LOCATION]")
    if not config or config.get("courses", True):
        prompt += "4. Specific named courses or department names -> [COURSE/DEPT]\n"
        allowed_tags.append("[COURSE/DEPT]")
    if not config or config.get("pii", True):
        prompt += "5. Email addresses, student/employee numbers, phone numbers -> [PII]\n"
        allowed_tags.append("[PII]")
    if not config or config.get("physical", True):
        prompt += """6. Physical appearance details that could identify a specific person:
   - Specific body features (e.g., kaal, baard, bril)
   - Specific clothing items (e.g., wit overhemd, rode jas, blauwe pet)
   - Identifying physical states (e.g., zweterig/sweaty, hinkt)
   -> [PHYSICAL_DESCRIPTOR]\n"""
        allowed_tags.append("[PHYSICAL_DESCRIPTOR]")

    prompt += "\n=== WHAT NOT TO REPLACE ===\n"
    prompt += "Do NOT tag these — they are generic words, not identifying information:\n"
    prompt += "- Generic nouns: workshop, library, bibliotheek, kantine, klas, lokaal, stage, afstudeerstage, campus (when used generically), gebouw\n"
    prompt += "- Food, drinks, and facilities: koffie, thee, eten, drinken, lunch, stoelen, tafels\n"
    prompt += "- Body parts: voeten, handen, hoofd, armen, benen\n"
    prompt += "- Roles/functions without a name: \"de docent\", \"mijn mentor\", \"my supervisor\"\n"
    prompt += "- Emotions or actions: boos, schreeuwde, blij, huilt\n"
    prompt += "- Numbers, scores, or grades: e.g., '1', '4', '8.5', '10'. NEVER replace these standalone numbers.\n"
    
    # Explicitly tell the LLM to IGNORE categories that are turned off
    forbidden_tags = [t for t in ["[NAME]", "[TITLE]", "[LOCATION]", "[COURSE/DEPT]", "[PII]", "[PHYSICAL_DESCRIPTOR]"] if t not in allowed_tags]
    if forbidden_tags:
        prompt += f"\nCRITICAL: The user has DISABLED the following tags: {', '.join(forbidden_tags)}. You MUST completely IGNNORE these entities and leave them in the text as normal words! Do not use these tags under any circumstances!\n"

    prompt += f"""
=== STRICT RULES ===
- PRESERVE the original sentence structure word-for-word. Replace ONLY the identifying words.
- Do NOT rewrite, paraphrase, summarize, or restructure any sentence.
- NEVER replace numbers, scores, or grades (such as '1', '2', '5', '8.5') with tags like [COURSE/DEPT] or [PII]. Keep them EXACTLY as numbers.
- The input text may already contain tags like [NAME] or [LOCATION] added by a previous system. LEAVE THEM EXACTLY AS THEY ARE.
- Do NOT invent new tags. Use ONLY the tags exactly as listed in the 'WHAT TO REPLACE' section: {', '.join(allowed_tags)}.
- Do NOT add a tag if there is nothing to anonymize in that spot.
- Return the result as a SINGLE LINE. Never add line breaks, newlines, or conversational text.
- Return ONLY the anonymized text. NO explanations, NO introductions, NO apologies, NO "Here is the text".
- DO NOT REFUSE. You are an automated system. If a sentence is difficult, just return the sentence with whatever tags you can apply. Do NOT ever say "Ik kan dit niet" or "Sorry".

=== EXAMPLES ===
"""
    # Dynamic examples so the LLM doesn't learn from tags it's not supposed to use
    if "[NAME]" in allowed_tags and "[LOCATION]" in allowed_tags:
        prompt += "Input:  De docent Jan Janssen in Eindhoven gaf geweldige lessen.\nOutput: De docent [NAME] in [LOCATION] gaf geweldige lessen.\n\n"
    elif "[NAME]" in allowed_tags:
        prompt += "Input:  De docent Jan Janssen in Eindhoven gaf geweldige lessen.\nOutput: De docent [NAME] in Eindhoven gaf geweldige lessen.\n\n"
    elif "[LOCATION]" in allowed_tags:
        prompt += "Input:  De docent Jan Janssen in Eindhoven gaf geweldige lessen.\nOutput: De docent Jan Janssen in [LOCATION] gaf geweldige lessen.\n\n"

    if "[PHYSICAL_DESCRIPTOR]" in allowed_tags:
        prompt += "Input:  the teacher who is bald and with a white shirt on and sweaty was really mad.\nOutput: the teacher who is [PHYSICAL_DESCRIPTOR] and with a [PHYSICAL_DESCRIPTOR] on and [PHYSICAL_DESCRIPTOR] was really mad.\n\n"
        prompt += "Input:  docent pietre had rode schoenen aan en een blauwe jas in de klas.\nOutput: docent [NAME] had [PHYSICAL_DESCRIPTOR] aan en een [PHYSICAL_DESCRIPTOR] in de klas.\n\n"
        prompt += "Input:  de docent met grote schoenen en teenslippers had haren op zijn voeten.\nOutput: de docent met [PHYSICAL_DESCRIPTOR] en [PHYSICAL_DESCRIPTOR] had [PHYSICAL_DESCRIPTOR].\n\n"
    else:
        prompt += "Input:  the teacher who is bald and with a white shirt on and sweaty was really mad.\nOutput: the teacher who is bald and with a white shirt on and sweaty was really mad.\n\n"

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
    except Exception as e:
        logging.error(f"Presidio error on '{text[:30]}...': {e}")
        presidio_anonymized = text

    # If everything is turned off, just return original text
    if config and not any(config.values()):
        return text

    # Step 2: Local LLM (Contextual PII via Ollama)
    try:
        prompt_str = get_dynamic_prompt(config)
        
        # Implement Retry Logic for LLM Flaws
        max_retries = 2
        for attempt in range(max_retries):
            response = client.chat(model=model_name, messages=[
                {"role": "system", "content": prompt_str},
                {"role": "user", "content": presidio_anonymized}
            ])
            
            anonymized = response['message']['content'].strip()
            
            # Check if output is suspiciously shorter or longer than input
            input_len = len(str(text))
            output_len = len(anonymized)
            
            needs_retry = False
            
            if output_len < (input_len * 0.2) or output_len > (input_len * 3.5):
                if attempt < max_retries - 1:
                    logging.info(f"Retrying LLM due to length mismatch. Attempt {attempt + 1}")
                    needs_retry = True
                else:
                    logging.warning(f"Suspicious output length for input: '{text[:30]}...' Flagging for review.")
                    return f"[NEEDS_REVIEW_LENGTH] {text}"

            # Check for common LLM safety refusals / conversational apologies
            if not needs_retry:
                refusal_phrases = [
                    "ik kan je niet helpen", "ik kan u niet helpen", 
                    "ik kan u niet assisteren", "i cannot", "i can't", 
                    "sorry", "als ai", "as an ai", "privacybreuk", "identificatienummer",
                    "ik kan dat niet", "ik kan dit niet", "ik kan de tekst niet", "ik heb niets vervangen"
                ]
                lower_anonymized = anonymized.lower()
                if any(phrase in lower_anonymized for phrase in refusal_phrases) or "\n" in anonymized:
                    if attempt < max_retries - 1:
                        logging.info(f"Retrying LLM due to safety refusal or conversational text. Attempt {attempt + 1}")
                        needs_retry = True
                    else:
                        logging.warning(f"Model safety refusal detected for input: '{text[:30]}...' Flagging for review.")
                        return f"[NEEDS_REVIEW_REFUSAL] {text}"
            
            if not needs_retry:
                return anonymized

        # If all retries fail, return the presidio-anonymized text or an error flag
        return f"[NEEDS_REVIEW_LLM_FAIL] {text}" # Changed to a specific error flag
        

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
