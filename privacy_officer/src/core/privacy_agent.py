import os
import re
import json
import asyncio
from typing import Optional, Set
import ollama
from openai import OpenAI, AsyncOpenAI
import pandas as pd
import logging
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException
from transformers import pipeline as hf_pipeline

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# LLM_BACKEND selects which inference server to use: "vllm" (default) or "ollama".
LLM_BACKEND = os.getenv('LLM_BACKEND', 'vllm')

# vLLM — OpenAI-compatible API server. Defaults work for Docker Compose setup.
VLLM_HOST = os.getenv('VLLM_HOST', 'http://localhost:8001')
vllm_client = OpenAI(base_url=f"{VLLM_HOST}/v1", api_key="not-needed")
vllm_async_client = AsyncOpenAI(base_url=f"{VLLM_HOST}/v1", api_key="not-needed")

# Ollama — kept as fallback backend.
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
# httpx (used by ollama-python) defaults to ~60s read timeout if unset, which aborts
# /api/chat while the server is still loading a large model into VRAM (see Ollama logs: 1m0s).
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "600"))
ollama_client = ollama.Client(host=OLLAMA_HOST, timeout=OLLAMA_TIMEOUT_SECONDS)

logging.info(f"LLM backend: {LLM_BACKEND}")
if LLM_BACKEND == 'vllm':
    logging.info(f"Connecting to vLLM at: {VLLM_HOST}")
else:
    logging.info(f"Connecting to Ollama at: {OLLAMA_HOST} (HTTP timeout {OLLAMA_TIMEOUT_SECONDS}s)")

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
    # FLOOR_REFERENCE: Floor indicators identifying a physical location within a building.
    # Catches "3e etage", "2e etage" (numeric ordinal) and "derde etage", "tweede etage" (written ordinal).
    {
        "entity": "FLOOR_REFERENCE",
        "patterns": [
            Pattern(name="floor_numeric", regex=r'\b\d+[e]\s+etage\b', score=0.9),
            Pattern(name="floor_written", regex=r'\b(?:eerste|tweede|derde|vierde|vijfde|zesde|zevende|achtste|negende|tiende)\s+etage\b', score=0.9),
        ],
        "context": ["etage", "verdieping", "gebouw"],
        "comment": "Catches '3e etage', 'derde etage'. High score — 'etage' is unambiguous.",
    },
    # NL_BSN: Dutch burgerservicenummer. Formatted (123.45.678) caught at 0.95;
    # bare 9-digit (123456789) at 0.75 with context to suppress false positives.
    {
        "entity": "NL_BSN",
        "patterns": [
            Pattern(name="nl_bsn_dots", regex=r'\b\d{3}\.\d{2}\.\d{3}\b', score=0.95),
            Pattern(name="nl_bsn_plain", regex=r'\b\d{9}\b', score=0.75),
        ],
        "context": ["bsn", "burgerservicenummer", "sofinummer", "identificatie"],
        "comment": "Formatted variant is unambiguous. Plain 9-digit needs context to avoid matching random numbers.",
    },
    # DUTCH_POSTCODE: Dutch postal code (4 digits + 2 uppercase letters, space optional).
    {
        "entity": "DUTCH_POSTCODE",
        "patterns": [
            Pattern(name="dutch_postcode", regex=r'\b\d{4}\s?[A-Z]{2}\b', score=0.9),
        ],
        "context": ["postcode", "adres", "straat", "woonplaats", "zip"],
        "comment": "Catches 3061 AW and 3061AW. Format is NL-specific so false positives are rare.",
    },
    # DUTCH_HONORIFIC: Dutch honorifics/titles that spaCy NER misclassifies as PERSON.
    # Replaced with [TITLE] so they are anonymized correctly instead of being tagged [NAME].
    {
        "entity": "DUTCH_HONORIFIC",
        "patterns": [
            Pattern(name="dutch_honorific", regex=r'\b(?:Mevrouw|mevrouw|Meneer|meneer|Mevr\.|mevr\.|Dhr\.|dhr\.|heer|Heer)\b', score=0.9),
        ],
        "context": None,
        "comment": "Catches Mevrouw/Meneer/heer which spaCy wrongly tags as PERSON → [NAME]. Explicit regex gives [TITLE] instead.",
    },
    # DUTCH_PHONE: Dutch mobile numbers in 06-XXXXXXXX format missed by Presidio's built-in PHONE_NUMBER.
    {
        "entity": "DUTCH_PHONE",
        "patterns": [
            Pattern(name="dutch_mobile", regex=r'\b06[-\s]\d{2}[-\s]?\d{2}[-\s]?\d{2}[-\s]?\d{2}\b', score=0.9),
            Pattern(name="dutch_mobile_intl", regex=r'\b\+316\d{8}\b', score=0.95),
        ],
        "context": None,
        "comment": "Catches 06-12345678, 06 12 34 56 78, +31612345678. Built-in PHONE_NUMBER misses the dash format.",
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
    "FLOOR_REFERENCE": OperatorConfig("replace", {"new_value": "[LOCATION]"}),
    "NL_BSN": OperatorConfig("replace", {"new_value": "[PII]"}),
    "DUTCH_POSTCODE": OperatorConfig("replace", {"new_value": "[LOCATION]"}),
    "DUTCH_HONORIFIC": OperatorConfig("replace", {"new_value": "[TITLE]"}),
    "DUTCH_PHONE": OperatorConfig("replace", {"new_value": "[PII]"}),
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
    if config.get("titles", True):
        operators["DUTCH_HONORIFIC"] = OperatorConfig("replace", {"new_value": "[TITLE]"})
    else:
        operators["DUTCH_HONORIFIC"] = OperatorConfig("keep")
    if config.get("pii", True):
        operators["EMAIL_ADDRESS"] = OperatorConfig("replace", {"new_value": "[PII]"})
        operators["PHONE_NUMBER"] = OperatorConfig("replace", {"new_value": "[PII]"})
        operators["STUDENT_NUMBER"] = OperatorConfig("replace", {"new_value": "[PII]"})
        operators["USERNAME"] = OperatorConfig("replace", {"new_value": "[PII]"})
        operators["OBFUSCATED_EMAIL"] = OperatorConfig("replace", {"new_value": "[PII]"})
        operators["BUILDING_OR_ROOM"] = OperatorConfig("replace", {"new_value": "[PII]"})
        operators["DUTCH_PHONE"] = OperatorConfig("replace", {"new_value": "[PII]"})
    else:
        for e in ("EMAIL_ADDRESS", "PHONE_NUMBER", "STUDENT_NUMBER", "USERNAME", "OBFUSCATED_EMAIL", "BUILDING_OR_ROOM", "DUTCH_PHONE"):
            operators[e] = OperatorConfig("keep")
    if config.get("floors", True):
        operators["FLOOR_REFERENCE"] = OperatorConfig("replace", {"new_value": "[LOCATION]"})
    else:
        operators["FLOOR_REFERENCE"] = OperatorConfig("keep")
    if config.get("bsn", True):
        operators["NL_BSN"] = OperatorConfig("replace", {"new_value": "[PII]"})
    else:
        operators["NL_BSN"] = OperatorConfig("keep")
    if config.get("postcode", True):
        operators["DUTCH_POSTCODE"] = OperatorConfig("replace", {"new_value": "[LOCATION]"})
    else:
        operators["DUTCH_POSTCODE"] = OperatorConfig("keep")
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


def parse_llm_json_response(raw: str) -> Optional[dict]:
    """
    Parse a JSON object from LLM output. Qwen/Ollama usually return clean JSON; Gemma and others
    may wrap content in markdown fences or add prose despite format=\"json\".
    """
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()

    def _try_load(fragment: str) -> Optional[dict]:
        try:
            obj = json.loads(fragment)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None

    direct = _try_load(s)
    if direct is not None:
        return direct

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", s, re.IGNORECASE)
    if fence:
        inner = _try_load(fence.group(1).strip())
        if inner is not None:
            logging.info("Parsed LLM JSON from markdown code fence (model returned extra wrapping).")
            return inner

    start = s.find("{")
    if start >= 0:
        try:
            obj, _ = json.JSONDecoder().raw_decode(s[start:])
            if isinstance(obj, dict):
                logging.info("Parsed LLM JSON via raw_decode (leading/trailing non-JSON text stripped).")
                return obj
        except json.JSONDecodeError:
            pass

    return None


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

    prompt += "\n=== STRICT RULES ===\n"
    prompt += "1. The strings in your JSON arrays MUST be EXACT substrings from the input text. Do not correct spelling or alter capitalization.\n"
    prompt += "2. DO NOT extract generic words (like 'workshop', 'bibliotheek', 'kantine', 'eten', 'voeten', 'blij').\n"
    prompt += "3. DO NOT extract standalone numbers or grades (like '1', '4', '8.5').\n"
    prompt += "4. The output must be parsable by Python's json.loads().\n"

    # Explicit prohibitions for disabled categories so the LLM doesn't smuggle them into other categories
    if config and not config.get("titles", True):
        prompt += "5. DO NOT extract honorifics or titles (Meneer, Mevrouw, Dhr., Mevr., Dr., docent, mentor, coach, begeleider, professor) — not even as part of a name string.\n"
    if config and not config.get("names", True):
        prompt += "6. DO NOT extract personal names of any kind.\n"
    if config and not config.get("locations", True):
        prompt += "7. DO NOT extract locations, cities, campuses or street names.\n"
    if config and not config.get("physical", True):
        prompt += "8. DO NOT extract physical appearance details.\n"
    if config and not config.get("courses", True):
        prompt += "9. DO NOT extract course names or department names.\n"
    return prompt

# Accepted layer IDs: "1"=Presidio, "2"=EU-PII-Safeguard, "3"=LLM. None = all layers.
VALID_LAYER_IDS: Set[str] = {"1", "2", "3"}


async def anonymize_text_async(
    text: str,
    model_name: str = 'aya-expanse:8b',
    config: Optional[dict] = None,
    layers: Optional[Set[str]] = None
) -> str:
    """Async version of anonymize_text. Layers 1+2 run sync; layer 3 LLM call is awaited."""
    if not isinstance(text, str) or not text.strip():
        return text

    # Layer 1: Presidio (sync, fast)
    if layers is None or "1" in layers:
        try:
            try:
                lang = detect(text)
                if lang not in ["nl", "en"]:
                    lang = "nl"
            except LangDetectException:
                lang = "nl"
            results = analyzer.analyze(text=text, language=lang)
            operators = build_presidio_operators(config)
            anonymized_result = anonymizer.anonymize(text=text, analyzer_results=results, operators=operators)
            presidio_anonymized = anonymized_result.text
        except Exception as e:
            logging.error(f"Presidio error on '{text[:30]}...': {e}")
            presidio_anonymized = text
    else:
        presidio_anonymized = text

    if config and not any(config.values()):
        return text

    # Layer 2: EU-PII-Safeguard (sync, fast)
    if layers is None or "2" in layers:
        eu_pii_anonymized = eu_pii_safeguard_anonymize(presidio_anonymized, config)
    else:
        eu_pii_anonymized = presidio_anonymized

    # Layer 3: LLM (async I/O)
    if layers is None or "3" in layers:
        try:
            prompt_str = get_dynamic_prompt(config)
            messages = [
                {"role": "system", "content": prompt_str},
                {"role": "user", "content": eu_pii_anonymized},
            ]

            if LLM_BACKEND == 'vllm':
                completion = await vllm_async_client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0,
                )
                raw_content = completion.choices[0].message.content.strip()
            else:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        ollama_client.chat, model=model_name, messages=messages, format="json"
                    ),
                    timeout=OLLAMA_TIMEOUT_SECONDS,
                )
                raw_content = response['message']['content'].strip()

            extracted_entities = parse_llm_json_response(raw_content)
            if extracted_entities is None:
                logging.error(f"Failed to parse JSON for input: {text[:30]}")
                return f"[NEEDS_REVIEW_ERROR] {text}"

            anonymized = eu_pii_anonymized
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
                    entities.sort(key=len, reverse=True)
                    for entity in entities:
                        if isinstance(entity, str) and entity and entity in anonymized:
                            pattern = re.compile(re.escape(entity), re.IGNORECASE)
                            new_anonymized = pattern.sub(tag, anonymized)
                            if new_anonymized != anonymized:
                                llm_replaced.append(f"'{entity}' ({category} → {tag})")
                                anonymized = new_anonymized

            if llm_replaced:
                logging.info(f"LLM caught {len(llm_replaced)} additional entities: {', '.join(llm_replaced)}")

            return anonymized

        except asyncio.TimeoutError:
            logging.error(
                f"Ollama timeout after {OLLAMA_TIMEOUT_SECONDS}s on '{text[:30]}...'"
            )
            return f"[NEEDS_REVIEW_TIMEOUT] {text}"
        except Exception as e:
            logging.error(f"LLM error on '{text[:30]}...': {e}")
            return f"[NEEDS_REVIEW_ERROR] {text}"
    else:
        return eu_pii_anonymized


async def process_dataframe_async(
    df: pd.DataFrame,
    text_column: str,
    model_name: str = 'aya-expanse:8b',
    config: Optional[dict] = None,
    progress_state: Optional[dict] = None,
    layers: Optional[Set[str]] = None,
    batch_size: int = 15
) -> pd.DataFrame:
    """Async version of process_dataframe. Processes rows in concurrent batches of batch_size."""
    logging.info(f"Starting async anonymization using model: {model_name}. Total rows: {len(df)}, batch size: {batch_size}")
    processed_df = df.copy()
    texts = processed_df[text_column].tolist()
    total_rows = len(texts)
    anonymized_texts = []

    for batch_start in range(0, total_rows, batch_size):
        batch = texts[batch_start:batch_start + batch_size]
        if progress_state is not None:
            # Set visible status before the batch starts so UI doesn't appear frozen.
            progress_state["status"] = f"Processing items {batch_start + 1}-{min(batch_start + batch_size, total_rows)} of {total_rows}..."
        tasks = [anonymize_text_async(text, model_name, config, layers) for text in batch]
        results = await asyncio.gather(*tasks)
        anonymized_texts.extend(results)

        done = min(batch_start + batch_size, total_rows)
        if progress_state is not None:
            progress_state["percentage"] = int(done / total_rows * 100)
            progress_state["status"] = f"Processing items {batch_start + 1}–{done} of {total_rows}..."

    processed_df[f'anonymized_{text_column}'] = anonymized_texts

    if progress_state is not None:
        progress_state["percentage"] = 100
        progress_state["status"] = "Completed!"

    logging.info("Async anonymization process completed.")
    return processed_df


