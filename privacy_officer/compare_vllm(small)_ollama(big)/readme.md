# PII Redaction Performance: Small vs Large LLMs

This document compares two LLM backends used in the final stage of the local PII redaction pipeline.

## Pipeline Context

The anonymization flow has three layers:

1. **Layer 1 - Microsoft Presidio**
  Fast NER/regex pass for direct identifiers.
2. **Layer 2 - EU-Safeguard model**
  Specialized entity and pattern pass for sensitive data.
3. **Layer 3 - LLM**
  Contextual pass for indirect identifiers that rule-based methods miss.

This benchmark focuses on **Layer 3 behavior** on the same dataset.

## Test Setup

- **Dataset size:** 676 open-text survey rows
- **Dataset file:** [`safe_cleaned_survey_long_format_q(all).csv`](./safe_cleaned_survey_long_format_q%28all%29.csv)
- **Hardware:** NVIDIA GeForce RTX 4050
- **VRAM:** 6 GB
- **Execution mode:** asynchronous
- **Batch size:** 5 rows at once

## Results


| Model                     | Engine | Size / Quantization | Execution Time | Rows Redacted |
| ------------------------- | ------ | ------------------- | -------------- | ------------- |
| `Qwen2.5-3B-Instruct-AWQ` | vLLM   | 3B, AWQ             | ~3 minutes     | 136           |
| `aya-expanse:8b`          | Ollama | 8B, 4-bit           | ~81 minutes    | 352           |

### Model links and short explanation

- **Qwen2.5-3B-Instruct-AWQ**: [Hugging Face model page](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-AWQ)  
  A compact 3B instruct model quantized with AWQ (4-bit), designed to run fast and memory-efficient on smaller GPUs.

- **aya-expanse:8b**: [Ollama model page](https://ollama.com/library/aya-expanse:8b)  
  A larger 8B multilingual chat model in Ollama format, usually better at nuanced context but heavier and slower on low-VRAM laptops.


## Quality Findings

### Aya 8B (Ollama)

- Redacted more rows, but also produced more **false positives**.
- Sometimes replaced generic non-sensitive nouns.
- Example behavior:
  - `"you have to go to the desk physically"` -> `"... go to the [LOCATION] physically"`
  - `"advanced coding project"` -> `"[LOCATION] project"`

### Qwen 3B AWQ (vLLM)

- Redacted fewer rows, but with better contextual precision.
- Left neutral terms untouched more often.
- Example behavior:
  - Kept `"desk"` unchanged where context was non-identifying.
  - `"teachers in my department"` -> `"[TITLE] in my department"`
  - `"International Relations"` -> `"[COURSE/DEPT]"`

## Interpretation

- **Speed:** Qwen 3B AWQ was dramatically faster on this hardware.
- **Data utility:** Qwen 3B AWQ preserved more useful non-sensitive text.
- **Memory constraints:** On 6 GB VRAM, the 8B pipeline likely incurred heavier memory pressure/offloading, driving runtime up.

## Practical Recommendation

- Use **Qwen 3B AWQ + vLLM** for fast, stable local processing and cleaner output.
- Use **Aya 8B + Ollama** only when you intentionally prioritize aggressive masking and can accept long runtime.

