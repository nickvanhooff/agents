import re
import logging
from typing import Optional

import torch
from transformers import pipeline as hf_pipeline

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

_device = 0 if torch.cuda.is_available() else -1
logging.info(f"Loading tabularisai/eu-pii-safeguard model on {'GPU (cuda:0)' if _device == 0 else 'CPU'} (downloads on first run)...")
try:
    eu_pii_ner = hf_pipeline(
        "token-classification",
        model="tabularisai/eu-pii-safeguard",
        aggregation_strategy="simple",
        device=_device,
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


def _apply_eu_pii_entities(text: str, entities: list, config: Optional[dict] = None) -> str:
    """Apply a list of eu-pii-safeguard entity dicts to a single text."""
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


def eu_pii_safeguard_anonymize(text: str, config: Optional[dict] = None) -> str:
    """Layer 2: run tabularisai/eu-pii-safeguard over a single text."""
    if eu_pii_ner is None or not text.strip():
        return text

    try:
        entities = eu_pii_ner(text)
    except Exception as e:
        logging.error(f"eu-pii-safeguard error: {e}")
        return text

    return _apply_eu_pii_entities(text, entities, config)


def eu_pii_safeguard_anonymize_batch(texts: list, config: Optional[dict] = None) -> list:
    """
    Run eu-pii-safeguard on a list of texts in one pipeline call.
    Returns a list of anonymized texts in the same order.
    """
    if eu_pii_ner is None or not texts:
        return texts

    try:
        # Pass batch_size so the transformer processes all texts in one forward pass
        # instead of the default of 1-at-a-time.
        batch_entities = eu_pii_ner(texts, batch_size=len(texts))
    except Exception as e:
        logging.error(f"eu-pii-safeguard batch error: {e}")
        return texts

    return [
        _apply_eu_pii_entities(text, entities, config)
        for text, entities in zip(texts, batch_entities)
    ]
