import logging
import re
from typing import Optional

from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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


anonymizer = AnonymizerEngine()
register_custom_presidio_recognizers(analyzer)

_POSSESSIVE_RE = re.compile(r"[''][sS]\b")
_QUOTED_RE = re.compile(r'"([^"]+)"')
_ALLCAPS_WORD_RE = re.compile(r'\b[A-Z]{2,}\b')


def _normalize_for_ner(text: str) -> str:
    """
    Normalize text for NER while preserving exact string length so offsets stay valid.
    - "SMITH"  -> "Smith"  (ALLCAPS -> Title case, same length)
    - "Smith"  -> " Smith " (surrounding quotes become spaces, same length)
    - Smith's  -> Smith    (possessive 's becomes spaces, same length)
    """
    text = _QUOTED_RE.sub(lambda m: f" {m.group(1)} ", text)
    text = _ALLCAPS_WORD_RE.sub(lambda m: m.group(0).capitalize(), text)
    text = _POSSESSIVE_RE.sub("  ", text)
    return text


def anonymize_with_presidio(text: str, config: Optional[dict] = None) -> str:
    """Run Layer 1 Presidio on a single text. Returns anonymized text."""
    try:
        lang = detect(text)
        if lang not in ["nl", "en"]:
            lang = "nl"
    except LangDetectException:
        lang = "nl"
    results = analyzer.analyze(text=text, language=lang)
    operators = build_presidio_operators(config)
    return anonymizer.anonymize(text=text, analyzer_results=results, operators=operators).text


def collect_presidio_spans(text: str, config: Optional[dict] = None) -> list:
    """
    Run Presidio analysis and return (start, end, tag) spans without applying masking.
    Used for late-masking mode where all layers collect first, mask once at the end.
    """
    try:
        try:
            lang = detect(text)
            if lang not in ["nl", "en"]:
                lang = "nl"
        except LangDetectException:
            lang = "nl"

        results = analyzer.analyze(text=_normalize_for_ner(text), language=lang)
        operators = build_presidio_operators(config)

        spans = []
        for result in results:
            op = operators.get(result.entity_type) or operators.get("DEFAULT")
            if op and op.operator_name == "replace":
                tag = op.params.get("new_value", "[PII]")
                spans.append((result.start, result.end, tag))
        return spans
    except Exception as e:
        logging.error(f"Presidio collect error on '{str(text)[:30]}...': {e}")
        return []
