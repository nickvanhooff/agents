import asyncio
import logging
from typing import Optional, Set

import pandas as pd

from src.core.layers.layer1_presidio import anonymize_with_presidio
from src.core.layers.layer2_eu_pii import eu_pii_safeguard_anonymize_batch
from src.core.layers.layer3_llm import anonymize_with_llm_async

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Accepted layer IDs: "1"=Presidio, "2"=EU-PII-Safeguard, "3"=LLM. None = all layers.
VALID_LAYER_IDS: Set[str] = {"1", "2", "3"}


async def anonymize_text_async(
    text: str,
    model_name: str = 'aya-expanse:8b',
    config: Optional[dict] = None,
    layers: Optional[Set[str]] = None
) -> str:
    """Anonymize a single text through the selected layers."""
    if not isinstance(text, str) or not text.strip():
        return text

    if config and not any(config.values()):
        return text

    # Layer 1: Presidio
    if layers is None or "1" in layers:
        try:
            result = anonymize_with_presidio(text, config)
        except Exception as e:
            logging.error(f"Presidio error on '{text[:30]}...': {e}")
            result = text
    else:
        result = text

    # Layer 2: EU-PII-Safeguard (single-text path for standalone calls)
    if layers is None or "2" in layers:
        batch_out = eu_pii_safeguard_anonymize_batch([result], config)
        result = batch_out[0]

    # Layer 3: LLM
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
    batch_size: int = 1000
) -> pd.DataFrame:
    """Anonymize all rows in df[text_column]. Layer 2 runs as a single batch call per chunk."""
    logging.info(f"Starting async anonymization using model: {model_name}. Total rows: {len(df)}, batch size: {batch_size}")
    processed_df = df.copy()
    texts = processed_df[text_column].tolist()
    total_rows = len(texts)
    anonymized_texts = []

    for batch_start in range(0, total_rows, batch_size):
        batch = texts[batch_start:batch_start + batch_size]
        done_so_far = min(batch_start + batch_size, total_rows)

        if progress_state is not None:
            progress_state["status"] = f"Processing items {batch_start + 1}-{done_so_far} of {total_rows}..."

        # Layer 1: Presidio — sync, per text
        if layers is None or "1" in layers:
            layer1_out = []
            for t in batch:
                try:
                    layer1_out.append(anonymize_with_presidio(t, config))
                except Exception as e:
                    logging.error(f"Presidio error on '{str(t)[:30]}...': {e}")
                    layer1_out.append(t)
        else:
            layer1_out = list(batch)

        # Layer 2: EU-PII-Safeguard — one batch call for the whole chunk
        if layers is None or "2" in layers:
            layer2_out = eu_pii_safeguard_anonymize_batch(layer1_out, config)
        else:
            layer2_out = layer1_out

        # Layer 3: LLM — async concurrent per text
        if layers is None or "3" in layers:
            tasks = [anonymize_with_llm_async(t, model_name, config) for t in layer2_out]
            results = list(await asyncio.gather(*tasks))
        else:
            results = layer2_out

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
