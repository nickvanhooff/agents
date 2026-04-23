import logging
import os
from typing import Optional

import torch
from transformers import pipeline as hf_pipeline

from src.core.layers.layer2_text_norm import normalize_for_ner

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

_DEVICE = 0 if torch.cuda.is_available() else -1
_OPF_MODEL_ID = "openai/privacy-filter"
_use_fp16 = os.environ.get("LAYER2_FP16", "").lower() in {"1", "true", "yes"}

logging.info(
    f"Loading {_OPF_MODEL_ID} (OpenAI privacy filter) on "
    f"{'GPU (cuda:0)' if _DEVICE == 0 else 'CPU'} (downloads on first run)..."
)
try:
    pipeline_kwargs = {
        "task": "token-classification",
        "model": _OPF_MODEL_ID,
        "aggregation_strategy": "simple",
        "device": _DEVICE,
    }
    if _DEVICE == 0 and _use_fp16:
        pipeline_kwargs["model_kwargs"] = {"torch_dtype": torch.float16}
        logging.info("LAYER2_FP16 enabled for openai/privacy-filter.")
    openai_privacy_filter_ner = hf_pipeline(**pipeline_kwargs)
    logging.info("openai/privacy-filter loaded successfully.")
except Exception as e:
    openai_privacy_filter_ner = None
    logging.warning(f"openai/privacy-filter failed to load: {e}. This Layer 2 option will be skipped.")


def _strip_bioes_prefix(label: str) -> str:
    """Normalize PER/LOC labels that may appear as B-private_person, I-..., etc."""
    s = (label or "").strip()
    for prefix in ("B-", "I-", "E-", "S-", "O-"):
        if len(s) > len(prefix) and s.startswith(prefix):
            return s[len(prefix) :]
    return s


def _opf_group_tag(entity_group: str) -> str:
    """
    Map OpenAI Privacy Filter entity groups to the same tag vocabulary as the rest
    of the pipeline. See model card: private_person, private_email, private_phone,
    private_address, private_url, private_date, account_number, secret.
    """
    label = _strip_bioes_prefix(str(entity_group or "")).lower()
    if label == "private_person":
        return "[NAME]"
    if label == "private_address":
        return "[LOCATION]"
    return "[PII]"


def _config_allows_tag(config: Optional[dict], tag: str) -> bool:
    if not config:
        return True
    if tag == "[NAME]":
        return bool(config.get("names", True))
    if tag == "[LOCATION]":
        return bool(config.get("locations", True))
    if tag == "[PII]":
        return bool(config.get("pii", True))
    return True


def _spans_for_one_text(text: str, entities: list, config: Optional[dict]) -> list:
    spans = []
    for ent in sorted(entities, key=lambda e: e["end"] - e["start"], reverse=True):
        span_text = text[ent["start"] : ent["end"]]
        if not span_text.strip() or len(span_text) < 2:
            continue
        tag = _opf_group_tag(str(ent.get("entity_group", "")))
        if not _config_allows_tag(config, tag):
            continue
        spans.append((ent["start"], ent["end"], tag))
    return spans


def openai_privacy_filter_collect_batch(
    texts: list, config: Optional[dict] = None
) -> list:
    """
    Run openai/privacy-filter on a list of texts; return span lists
    (start, end, tag) per text, same shape as eu_pii_collect_batch.
    Uses length-preserving NER normalization so offsets align with eu-pii.
    """
    if openai_privacy_filter_ner is None or not texts:
        return [[] for _ in texts]
    try:
        texts_for_ner = [normalize_for_ner(t) for t in texts]
        batch_entities = openai_privacy_filter_ner(
            texts_for_ner, batch_size=len(texts_for_ner)
        )
    except Exception as e:
        logging.error(f"openai/privacy-filter collect batch error: {e}")
        return [[] for _ in texts]

    return [_spans_for_one_text(t, ent, config) for t, ent in zip(texts, batch_entities)]
