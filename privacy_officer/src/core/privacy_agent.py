import os
import re
import json
from typing import Optional, Set
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
from transformers import pipeline as hf_pipeline

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

# -----------------------------------------------------------------------------
# PRESIDIO PATTERN DEFINITIONS (Layer 1 - Regex/NER)
# -----------------------------------------------------------------------------
# Central config for custom regex recognizers. Each entry: name, regex, score,
# entity type, optional context words (boost confidence when nearby).
# Score: 0.0-1.0; higher = more confident. Use 0.75-0.9 for generic patterns
# to avoid false positives while still catching real PII.
# -----------------------------------------------------------------------------

PRESIDIO_PATTERN_DEFINITIONS = [
    # STUDENT_NUMBER: Fontys-style 5-7 digit student IDs. No context needed.
    {
        "entity": "STUDENT_NUMBER",
        "patterns": [Pattern(name="student_number", regex=r'\b[0-9]{5,7}\b', score=0.85)],
        "context": None,
        "comment": "Catches e.g. 547795, 1234567. Caveat: may match random number sequences.",
    },
    # USERNAME: Social handles (@xxx) and usernames with underscores/digits (j_doe88, van_der_meer).
    # Context boosts confidence when "insta", "github", "account" etc. are nearby.
    # We avoid generic word-like patterns to prevent false positives on normal text.
    {
        "entity": "USERNAME",
        "patterns": [
            Pattern(name="at_handle", regex=r'@[\w]+', score=0.9),
            Pattern(name="underscore_username", regex=r'\b[\w]+(?:_[\w]+)+\b', score=0.75),
            Pattern(name="username_with_digits", regex=r'\b[a-zA-Z][a-zA-Z0-9_]{1,25}\d{2,}[a-zA-Z0-9_]*\b', score=0.75),
        ],
        "context": ["insta", "instagram", "github", "account", "handle", "username", "profiel", "genaamd", "bekend"],
        "comment": "Caveat: underscore pattern matches 'de_les' etc.; context helps. Digit pattern needs 2+ trailing digits.",
    },
    # OBFUSCATED_EMAIL: Dutch spelled-out emails ("x punt y apenstaartje z punt nl").
    # Requires "apenstaartje" (at) and "punt" (dot) to avoid generic matches.
    {
        "entity": "OBFUSCATED_EMAIL",
        "patterns": [
            Pattern(
                name="dutch_spelled_email",
                regex=r'[\w_]+(?:\s+(?:punt|\.)\s+[\w_]+)+\s+apenstaartje\s+[\w_]+(?:\s+(?:punt|\.)\s+[\w_]+)+',
                score=0.85,
            ),
        ],
        "context": ["mail", "mailen", "email", "bereiken", "contact"],
        "comment": "Catches e.g. 's punt van_der_meer apenstaartje student punt fontys punt nl'.",
    },
    # BUILDING_OR_ROOM: Room/block codes (R1, TQ 3.14, lokaal 2.05, gebouw R2).
    {
        "entity": "BUILDING_OR_ROOM",
        "patterns": [
            Pattern(name="room_code", regex=r'\b(?:R|TQ|TL|TX)\s*\d+(?:[.,]\d+)?\b', score=0.8),
            Pattern(name="lokaal_number", regex=r'\b(?:lokaal|gebouw|ruimte)\s+\d+(?:[.,]\d+)?\b', score=0.85),
        ],
        "context": ["lokaal", "gebouw", "lokaalnummer", "kamer", "ruimte", "lokaal"],
        "comment": "Catches R1, TQ 3.14, lokaal 2.05. Caveat: standalone 'R1' without context may be false positive.",
    },
]

# Operator mapping: which replacement tag to use per entity. DEFAULT=keep ignores
# entities we don't explicitly handle (e.g. DATE_TIME if we want to keep dates).
PRESIDIO_OPERATORS = {
    "PERSON": OperatorConfig("replace", {"new_value": "[NAME]"}),
    "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[PII]"}),
    "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[PII]"}),
    "STUDENT_NUMBER": OperatorConfig("replace", {"new_value": "[PII]"}),
    "LOCATION": OperatorConfig("replace", {"new_value": "[LOCATION]"}),
    "NRP": OperatorConfig("replace", {"new_value": "[NAME]"}),
    "USERNAME": OperatorConfig("replace", {"new_value": "[PII]"}),
    "OBFUSCATED_EMAIL": OperatorConfig("replace", {"new_value": "[PII]"}),
    "BUILDING_OR_ROOM": OperatorConfig("replace", {"new_value": "[PII]"}),
    "DEFAULT": OperatorConfig("keep"),
}


def register_custom_presidio_recognizers(analyzer_engine) -> None:
    """
    Register all custom Presidio pattern recognizers from PRESIDIO_PATTERN_DEFINITIONS.
    Creates recognizers for both nl and en so they run regardless of detected language.
    """
    for defn in PRESIDIO_PATTERN_DEFINITIONS:
        entity = defn["entity"]
        patterns = defn["patterns"]
        context = defn.get("context")
        for lang in ["nl", "en"]:
            rec = PatternRecognizer(
                supported_entity=entity,
                patterns=patterns,
                supported_language=lang,
                context=context,
            )
            analyzer_engine.registry.add_recognizer(rec)
    logging.info(f"Registered {len(PRESIDIO_PATTERN_DEFINITIONS)} custom Presidio recognizer types (nl+en).")


def build_presidio_operators(config: Optional[dict] = None) -> dict:
    """
    Build the operator dict for Presidio anonymizer. If config is provided,
    respect user toggles (names, locations, pii); otherwise use full PRESIDIO_OPERATORS.
    """
    if not config:
        return dict(PRESIDIO_OPERATORS)
    operators = {}
    if config.get("names", True):
        operators["PERSON"] = OperatorConfig("replace", {"new_value": "[NAME]"})
        operators["NRP"] = OperatorConfig("replace", {"new_value": "[NAME]"})
    else:
        operators["PERSON"] = OperatorConfig("keep")
        operators["NRP"] = OperatorConfig("keep")
    if config.get("locations", True):
        operators["LOCATION"] = OperatorConfig("replace", {"new_value": "[LOCATION]"})
    else:
        operators["LOCATION"] = OperatorConfig("keep")
    if config.get("pii", True):
        operators["EMAIL_ADDRESS"] = OperatorConfig("replace", {"new_value": "[PII]"})
        operators["PHONE_NUMBER"] = OperatorConfig("replace", {"new_value": "[PII]"})
        operators["STUDENT_NUMBER"] = OperatorConfig("replace", {"new_value": "[PII]"})
        operators["USERNAME"] = OperatorConfig("replace", {"new_value": "[PII]"})
        operators["OBFUSCATED_EMAIL"] = OperatorConfig("replace", {"new_value": "[PII]"})
        operators["BUILDING_OR_ROOM"] = OperatorConfig("replace", {"new_value": "[PII]"})
    else:
        for e in ("EMAIL_ADDRESS", "PHONE_NUMBER", "STUDENT_NUMBER", "USERNAME", "OBFUSCATED_EMAIL", "BUILDING_OR_ROOM"):
            operators[e] = OperatorConfig("keep")
    operators["DEFAULT"] = OperatorConfig("keep")
    return operators


register_custom_presidio_recognizers(analyzer)
anonymizer = AnonymizerEngine()

# Initialize eu-pii-safeguard (tabularisai/eu-pii-safeguard)
# Downloads ~1.1GB on first run, cached afterwards.
logging.info("Loading tabularisai/eu-pii-safeguard model (downloads on first run)...")
try:
    eu_pii_ner = hf_pipeline(
        "token-classification",
        model="tabularisai/eu-pii-safeguard",
        aggregation_strategy="simple",
        device=-1,  # CPU; set to 0 for GPU
    )
    logging.info("eu-pii-safeguard loaded successfully.")
except Exception as e:
    eu_pii_ner = None
    logging.warning(f"eu-pii-safeguard failed to load: {e}. Layer 2 will be skipped.")

# Map eu-pii-safeguard entity_group labels to replacement tags.
# Uses keyword matching so it stays robust against exact label name variants.
def _eu_pii_tag(entity_group: str) -> str:
    label = entity_group.upper()
    if any(k in label for k in ("NAME", "PERSON", "FIRSTNAME", "LASTNAME", "SURNAME", "GIVENNAME")):
        return "[NAME]"
    if any(k in label for k in ("CITY", "ADDRESS", "STREET", "LOCATION", "ZIPCODE", "POSTAL", "STATE", "COUNTRY", "REGION")):
        return "[LOCATION]"
    # Everything else (email, phone, IBAN, credit card, SSN, passport, tax ID,
    # username, IP, medical condition, age, gender, ethnicity, etc.) → [PII]
    return "[PII]"


def eu_pii_safeguard_anonymize(text: str, config: dict = None) -> str:
    """Layer 2: run tabularisai/eu-pii-safeguard over text already cleaned by Presidio."""
    if eu_pii_ner is None or not text.strip():
        return text

    try:
        entities = eu_pii_ner(text)
    except Exception as e:
        logging.error(f"eu-pii-safeguard error: {e}")
        return text

    if not entities:
        return text

    # Sort longest span first to avoid partial-match clobbering
    entities_sorted = sorted(entities, key=lambda e: e["end"] - e["start"], reverse=True)

    result = text
    replaced = []
    for ent in entities_sorted:
        span = text[ent["start"]:ent["end"]]
        if not span.strip():
            continue
        # Filter single-char spans: token classifiers often mislabel subword tokens
        # (e.g. "t" as FIRSTNAME), causing catastrophic replacement of all "t" in text.
        if len(span) < 2:
            continue

        label = ent["entity_group"]
        tag = _eu_pii_tag(label)

        # Respect config flags
        if config:
            if tag == "[NAME]" and not config.get("names", True):
                continue
            if tag == "[LOCATION]" and not config.get("locations", True):
                continue
            if tag == "[PII]" and not config.get("pii", True):
                continue

        pattern = re.compile(re.escape(span), re.IGNORECASE)
        new_result = pattern.sub(tag, result)
        if new_result != result:
            replaced.append(f"'{span}' ({label} → {tag})")
            result = new_result

    if replaced:
        logging.info(f"eu-pii-safeguard caught {len(replaced)} additional entities: {', '.join(replaced)}")

    return result


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

# Accepted layer IDs: "1"=Presidio, "2"=EU-PII-Safeguard, "3"=LLM. None = all layers.
VALID_LAYER_IDS: Set[str] = {"1", "2", "3"}


def anonymize_text(
    text: str,
    model_name: str = 'aya-expanse:8b',
    config: Optional[dict] = None,
    layers: Optional[Set[str]] = None
) -> str:
    """Anonymize text using selected layers. layers=None runs all layers; otherwise only IDs in layers (e.g. {'1','3'})."""
    if not isinstance(text, str) or not text.strip():
        return text

    # Step 1: Microsoft Presidio (Deterministic Regex/NER)
    if layers is None or "1" in layers:
        try:
            # Try to detect language, default to Dutch since data is mostly Dutch
            try:
                lang = detect(text)
                if lang not in ["nl", "en"]:
                    lang = "nl"
            except LangDetectException:
                lang = "nl"

            results = analyzer.analyze(text=text, language=lang)

            # Build operators from central config; respects user toggles (names, locations, pii)
            operators = build_presidio_operators(config)

            anonymized_result = anonymizer.anonymize(
                text=text,
                analyzer_results=results,
                operators=operators
            )
            presidio_anonymized = anonymized_result.text

            if results:
                entities_desc = [f"'{text[r.start:r.end]}' ({r.entity_type})" for r in results]
                type_counts = {}
                for r in results:
                    type_counts[r.entity_type] = type_counts.get(r.entity_type, 0) + 1
                logging.info(f"Presidio caught {len(results)} entities: {', '.join(entities_desc)}")
                logging.info(f"Presidio by type: {type_counts}")
                logging.info(f"Presidio output: '{presidio_anonymized}'")

        except Exception as e:
            logging.error(f"Presidio error on '{text[:30]}...': {e}")
            presidio_anonymized = text
    else:
        presidio_anonymized = text

    # If everything is turned off, just return original text
    if config and not any(config.values()):
        return text

    # Step 2: eu-pii-safeguard — catches named entities Presidio missed
    if layers is None or "2" in layers:
        eu_pii_anonymized = eu_pii_safeguard_anonymize(presidio_anonymized, config)
    else:
        eu_pii_anonymized = presidio_anonymized

    if layers is None or "3" in layers:
        try:
            prompt_str = get_dynamic_prompt(config)

            # Step 3: LLM — catches indirect/contextual PII that NER layers missed
            response = client.chat(model=model_name, messages=[
                {"role": "system", "content": prompt_str},
                {"role": "user", "content": eu_pii_anonymized}
                ], format="json")

            # safely parse the json response
            try:
                extracted_entities = json.loads(response['message']['content'].strip())
            except json.JSONDecodeError:
                logging.error(f"Failed to parse JSON for input: {text[:30]}")
                return f"[NEEDS_REVIEW_ERROR] {text}"

            anonymized = eu_pii_anonymized

            # We sort by length descending to replace larger phrases before smaller overlaps
            tag_map = {
                "names": "[NAME]",
                "titles": "[TITLE]",
                "locations": "[LOCATION]",
                "courses": "[COURSE/DEPT]",
                "pii": "[PII]",
                "physical": "[PHYSICAL_DESCRIPTOR]"
            }

            llm_replaced = []
            for category, entities in extracted_entities.items():
                if isinstance(entities, list) and category in tag_map:
                    tag = tag_map[category]
                    # Sort descending length so "John Doe" replaces before "John"
                    entities.sort(key=len, reverse=True)
                    for entity in entities:
                        if isinstance(entity, str) and entity and entity in anonymized:
                            # Case insensitive replacement via regex but preserving case of other words
                            pattern = re.compile(re.escape(entity), re.IGNORECASE)
                            new_anonymized = pattern.sub(tag, anonymized)
                            if new_anonymized != anonymized:
                                llm_replaced.append(f"'{entity}' ({category} → {tag})")
                                anonymized = new_anonymized

            if llm_replaced:
                logging.info(f"LLM caught {len(llm_replaced)} additional entities: {', '.join(llm_replaced)}")

            return anonymized

        except Exception as e:
            logging.error(f"LLM error on '{text[:30]}...': {e}")
            return f"[NEEDS_REVIEW_ERROR] {text}"
    else:
        return eu_pii_anonymized

def process_dataframe(
    df: pd.DataFrame,
    text_column: str,
    model_name: str = 'aya-expanse:8b',
    config: Optional[dict] = None,
    progress_state: Optional[dict] = None,
    layers: Optional[Set[str]] = None
) -> pd.DataFrame:
    """
    Apply anonymization to a text column. layers=None uses all layers; otherwise only the given IDs (e.g. {"1","3"}).
    """
    logging.info(f"Starting anonymization process using model: {model_name}. Total rows: {len(df)}")
    
    # Create a copy to avoid SettingWithCopyWarning, though we are returning a new df anyway.
    processed_df = df.copy()
    
    # Initialize a list to hold the results
    anonymized_texts = []
    
    total_rows = len(processed_df)
    
    # Iterate with tqdm for a progress bar
    for i, text in enumerate(tqdm(processed_df[text_column], desc="Anonymizing feedback")):
        anonymized_texts.append(anonymize_text(text, model_name, config, layers))
        
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
