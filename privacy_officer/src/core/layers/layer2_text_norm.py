"""Shared length-preserving text normalization for Layer 2 token classifiers."""

import re

_POSSESSIVE_RE = re.compile(r"['’][sS]\b")
_QUOTED_RE = re.compile(r'"([^"]+)"')
_ALLCAPS_WORD_RE = re.compile(r"\b[A-Z]{2,}\b")


def normalize_for_ner(text: str) -> str:
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
