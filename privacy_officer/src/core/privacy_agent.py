import asyncio
import logging
import re
from typing import Optional, Set

import pandas as pd

from src.core.layers.layer1_presidio import collect_presidio_spans
from src.core.layers.layer3_llm import anonymize_with_llm_async

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Accepted layer IDs: "1"=Presidio, "2"=EU-PII-Safeguard, "3"=LLM. None = all layers.
VALID_LAYER_IDS: Set[str] = {"1", "2", "3"}

# These words are never masked, regardless of config.
_NEVER_MASK_WORDS: Set[str] = {"meneer", "mevrouw"}

# Standalone honorifics suppressed when titles=False.
_HONORIFIC_WORDS: Set[str] = {
    "mevr.", "mevr", "dhr.", "dhr", "heer",
}

# Layer 2 transformer backend when layer "2" is active: Hugging Face model choice.
LAYER2_BACKEND_EU_PII = "eu_pii_safeguard"
LAYER2_BACKEND_OPENAI_OPF = "openai_privacy_filter"
VALID_LAYER2_BACKENDS: Set[str] = {LAYER2_BACKEND_EU_PII, LAYER2_BACKEND_OPENAI_OPF}


def collect_layer2_spans_batch(
    texts: list,
    config: Optional[dict],
    layer2_backend: str,
) -> list:
    """Dispatch to the selected Layer 2 token-classification backend."""
    if layer2_backend == LAYER2_BACKEND_OPENAI_OPF:
        from src.core.layers.layer2_openai_privacy_filter import (
            openai_privacy_filter_collect_batch,
        )

        return openai_privacy_filter_collect_batch(texts, config)
    if layer2_backend == LAYER2_BACKEND_EU_PII:
        from src.core.layers.layer2_eu_pii import eu_pii_collect_batch

        return eu_pii_collect_batch(texts, config)
    logging.warning(
        "Unknown layer2_backend %r, falling back to %s",
        layer2_backend,
        LAYER2_BACKEND_EU_PII,
    )
    from src.core.layers.layer2_eu_pii import eu_pii_collect_batch

    return eu_pii_collect_batch(texts, config)


def _build_carryforward_spans(texts: list, all_raw_spans: list) -> list:
    """
    Carry detected [NAME] entities forward across all texts in the batch.
    If a name is detected in one row but missed in another (weak NER context),
    add a literal regex match as an extra span for the missed row.
    Skips names shorter than 3 characters to avoid false positives.
    Config is implicitly respected: if names are disabled, no [NAME] spans exist to carry.
    """
    known_names: Set[str] = set()
    for text, spans in zip(texts, all_raw_spans):
        for start, end, tag in spans:
            if tag == "[NAME]":
                name = text[start:end].strip()
                if len(name) >= 3:
                    known_names.add(name)

    if not known_names:
        return [[] for _ in texts]

    extra_spans = []
    for text, spans in zip(texts, all_raw_spans):
        covered = [(s, e) for s, e, _ in spans]
        new_spans = []
        for name in known_names:
            pattern = re.compile(r'\b' + re.escape(name) + r'\b', re.IGNORECASE)
            for m in pattern.finditer(text):
                if not any(s <= m.start() < e or s < m.end() <= e for s, e in covered):
                    new_spans.append((m.start(), m.end(), "[NAME]"))
                    covered.append((m.start(), m.end()))
        extra_spans.append(new_spans)
    return extra_spans


def _process_chunk_sync(
    batch: list,
    config: Optional[dict],
    layers: Optional[Set[str]],
    layer2_backend: str,
) -> list:
    """
    Run sync Layer 1 + Layer 2 work outside the event loop.
    This keeps progress SSE responsive while heavy CPU/GPU work runs.
    """
    if layers is None or "1" in layers:
        layer1_spans = [collect_presidio_spans(t, config) for t in batch]
    else:
        layer1_spans = [[] for _ in batch]

    if layers is None or "2" in layers:
        layer2_spans = collect_layer2_spans_batch(list(batch), config, layer2_backend)
    else:
        layer2_spans = [[] for _ in batch]

    combined = [l1 + l2 for l1, l2 in zip(layer1_spans, layer2_spans)]
    combined = [_filter_spans(t, s, config) for t, s in zip(batch, combined)]
    carryforward = _build_carryforward_spans(batch, combined)

    return [
        apply_all_masks(text, extend_spans_for_original(text, spans + extra))
        for text, spans, extra in zip(batch, combined, carryforward)
    ]

_POSSESSIVE_RE = re.compile(r"['’][sS]\b")


def extend_spans_for_original(text: str, spans: list) -> list:
    """
    Adjust spans so they cover the original formatting that was stripped during NER normalization:
    - Possessive suffix: Smith's -> extend end by 2 to include 's
    - Surrounding quotes: "Smith" -> extend start/end by 1 to include the quotes
    Works for any detected name, independent of the specific value.
    """
    result = []
    for start, end, tag in spans:
        new_start, new_end = start, end
        if _POSSESSIVE_RE.match(text, new_end):
            new_end += 2
        if new_start > 0 and text[new_start - 1] == '"':
            new_start -= 1
        if new_end < len(text) and text[new_end] == '"':
            new_end += 1
        result.append((new_start, new_end, tag))
    return result


def _filter_spans(text: str, spans: list, config: Optional[dict]) -> list:
    """
    - Pure honorific spans (meneer/mevrouw) are always dropped.
    - Spans that START with an honorific + space have their start trimmed past the honorific,
      so "Mevrouw Jansen" becomes just "Jansen" — the name is still masked, the honorific not.
    - Other honorifics (heer, dhr., mevr.) are dropped when titles=False.
    """
    titles_on = not config or config.get("titles", True)
    result = []
    for s, e, tag in spans:
        span_text = text[s:e]
        word_lower = span_text.strip().rstrip(".").lower()

        # Pure honorific → always drop
        if word_lower in _NEVER_MASK_WORDS:
            continue
        if not titles_on and word_lower in _HONORIFIC_WORDS:
            continue

        # Span starts with a never-mask honorific followed by a space → trim the start
        new_s = s
        for hw in _NEVER_MASK_WORDS:
            prefix = hw + " "
            if span_text[:len(prefix)].lower() == prefix:
                new_s = s + len(prefix)
                break

        if new_s < e:
            result.append((new_s, e, tag))
    return result


def apply_all_masks(text: str, spans: list) -> str:
    """
    Apply a merged list of (start, end, tag) spans to text in one pass.
    Overlaps resolved by keeping the longest span.
    Applied right-to-left so earlier offsets stay valid during replacement.
    """
    if not spans:
        return text

    # Longest span wins when spans overlap
    sorted_spans = sorted(spans, key=lambda s: s[1] - s[0], reverse=True)
    selected = []
    for start, end, tag in sorted_spans:
        if not any(start < se and end > ss for ss, se, _ in selected):
            selected.append((start, end, tag))

    # Right-to-left so replacements don't shift offsets of earlier spans
    selected.sort(key=lambda s: s[0], reverse=True)
    result = text
    for start, end, tag in selected:
        result = result[:start] + tag + result[end:]
    return result


async def anonymize_text_async(
    text: str,
    model_name: str = 'aya-expanse:8b',
    config: Optional[dict] = None,
    layers: Optional[Set[str]] = None,
    layer2_backend: str = LAYER2_BACKEND_EU_PII,
) -> str:
    """
    Anonymize a single text. Layers 1+2 collect spans from the original text
    and mask once at the end. Layer 3 (LLM) runs on the masked result if selected.
    """
    if not isinstance(text, str) or not text.strip():
        return text
    if config and not any(config.values()):
        return text

    l1_spans = []
    if layers is None or "1" in layers:
        l1_spans = collect_presidio_spans(text, config)

    l2_spans = []
    if layers is None or "2" in layers:
        l2_spans = collect_layer2_spans_batch([text], config, layer2_backend)[0]

    combined_spans = _filter_spans(text, l1_spans + l2_spans, config)
    result = apply_all_masks(text, extend_spans_for_original(text, combined_spans))

    if layers is None or "3" in layers:
        result = await anonymize_with_llm_async(result, model_name, config)

    return result


async def process_dataframe_async(
    df: pd.DataFrame,
    text_column: str,
    model_name: str = 'aya-expanse:8b',
    config: Optional[dict] = None,
    progress_state: Optional[dict] = None,
    layers: Optional[Set[str]] = None,
    layer2_backend: str = LAYER2_BACKEND_EU_PII,
    batch_size: int = 1000
) -> pd.DataFrame:
    """Anonymize all rows in df[text_column]. Layer 2 runs as a single batch call per chunk."""
    logging.info(
        f"Starting async anonymization using model: {model_name}, layer2_backend: {layer2_backend}. "
        f"Total rows: {len(df)}, batch size: {batch_size}"
    )
    processed_df = df.copy()
    texts = processed_df[text_column].fillna("").astype(str).tolist()
    total_rows = len(texts)
    anonymized_texts = []

    for batch_start in range(0, total_rows, batch_size):
        batch = texts[batch_start:batch_start + batch_size]
        done_so_far = min(batch_start + batch_size, total_rows)

        if progress_state is not None:
            progress_state["status"] = f"Processing items {batch_start + 1}-{done_so_far} of {total_rows}..."

        pre_llm = await asyncio.to_thread(
            _process_chunk_sync,
            batch,
            config,
            layers,
            layer2_backend,
        )

        # Layer 3: LLM — async concurrent per text, runs on already-masked output
        if layers is None or "3" in layers:
            tasks = [anonymize_with_llm_async(t, model_name, config) for t in pre_llm]
            results = list(await asyncio.gather(*tasks))
        else:
            results = pre_llm

        anonymized_texts.extend(results)

        if progress_state is not None:
            progress_state["percentage"] = int(done_so_far / total_rows * 100)
            progress_state["status"] = f"Processing items {batch_start + 1}–{done_so_far} of {total_rows}..."

    processed_df[f'anonymized_{text_column}'] = anonymized_texts

    if progress_state is not None:
        progress_state["percentage"] = 100
        progress_state["status"] = "Completed!"

    logging.info("Async anonymization process completed.")
    return processed_df
