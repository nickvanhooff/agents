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

    return [
        apply_all_masks(text, extend_spans_for_original(text, l1 + l2))
        for text, l1, l2 in zip(batch, layer1_spans, layer2_spans)
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

    result = apply_all_masks(text, extend_spans_for_original(text, l1_spans + l2_spans))

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
