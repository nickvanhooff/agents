# PII Anonymization Architecture — Discussion Document

## Context

The Privacy Officer agent anonymizes Dutch student feedback using a **triple-layer** pipeline:
Presidio (NER + regex) → EU-PII-Safeguard (Specialized Transformer) → LLM (aya-expanse:8b via Ollama)

This document captures a technical discussion about improving that architecture, with the goal of replacing the LLM with something faster, more deterministic, and with less hallucination risk.

---

## Types of PII in student feedback

### Direct PII (structured)
Presidio already handles these well:
- Names → `[NAME]`
- Email addresses → `[PII]`
- Phone numbers → `[PII]`
- Student numbers (5–7 digits) → `[PII]`

### Named entity PII (contextual but explicit)
Standard NER models handle these:
- "docent **Jan Pieters**" → `[NAME]`
- "het kantoor in **Eindhoven**" → `[LOCATION]`
- "**Software Engineering 3**" course → `[COURSE/DEPT]`

### Indirect / quasi-identifier PII
*No standard NER model handles these reliably:*
- "de docent **met de kale kop**"
- "**de enige vrouw** in het ICT-team"
- "**mijn mentor** die altijd te laat komt"
- "de man **met de rode jas en de baard**"

These are descriptions that, in context, uniquely identify a person even though no named entity is present.

---

## Why replace the LLM layer?

| Problem | Impact |
|---|---|
| Non-deterministic output | Same input → different results on reruns |
| Hallucination | LLM can invent entities not in the text |
| Speed | ~2–5 seconds per row; 500 rows ≈ 30–40 min |
| RAM | llama3.1:8b requires 8–12 GB RAM |
| Auditability | Hard to explain to a DPO *why* something was redacted |

---

## Models evaluated

### Option A — `tabularisai/eu-pii-safeguard`
**Recommendation: use as Layer 2 (replaces most of the LLM's job)**

- Base model: XLM-RoBERTa-large
- Languages: all 26 EU official languages including **Dutch** (purpose-built for GDPR)
- Entity types: **42** — names, addresses, IBANs, medical conditions, IPs, usernames, tax IDs, and more
- Performance: 97% F1, all 26 languages above 95%
- Runs offline, CPU-capable, deterministic
- License: check model card

**What it catches that Presidio misses:** names in complex sentence structures, addresses written out in prose, IBANs, titles combined with names

**What it does NOT catch:** indirect/quasi-identifier PII (physical descriptors, implicit references)

---

### Option B — `iiiorg/piiranha-v1-detect-personal-information`
**Recommendation: lighter-weight alternative to Option A**

- Base model: microsoft/mdeberta-v3-base (~280M params)
- Languages: English, Spanish, French, German, Italian, **Dutch**
- Entity types: **17** — names, emails, phone, DOB, credit card, SSN, address, etc.
- Performance: 98.27% recall, 99.44% accuracy (multilingual test set)
- License: CC-BY-NC-ND 4.0 (non-commercial only)

Smaller and faster than eu-pii-safeguard, but fewer entity types and non-commercial license.

---

### Option C — `urchade/gliner_multi_pii-v1`
**Recommendation: avoid for Dutch**

- Trained on: English, French, German, Spanish, Italian, Portuguese
- **Dutch is NOT in the training data**
- Any Dutch capability is accidental cross-lingual transfer — unreliable

---

### Option D — `pdelobelle/robbert-v2-dutch-ner` (RobBERT)
**Recommendation: useful as a Presidio custom recognizer for Dutch names**

- Base model: RoBERTa fine-tuned on Dutch data (KU Leuven / CLiPS)
- Languages: Dutch only
- Entity types: 4 (PER, ORG, LOC, MISC) — not PII-specific
- Performance: F1 = 97.82% on Dutch CoNLL-2002 (best-in-class Dutch NER)

Best Dutch person/location name detection available, but too narrow to replace the LLM layer.

---

## The hard problem: indirect identification

No NER model detects indirect PII because it requires semantic reasoning, not span labeling.

### What does the industry do?

**The industrial standard is human review for indirect identifiers.**

Automated tools handle obvious PII; a human reviewer handles ambiguous cases.

### Layer 3 options compared

| Option | Dutch quality | Speed | Hallucination risk | Offline | Effort to add |
|---|---|---|---|---|---|
| llama3.2:3b (Ollama) | Good | ~1–2s/row | Medium | Yes | Already in setup |
| llama3.1:8b (Ollama) | Good | ~3–5s/row | Medium | Yes | Already in setup |
| mistral:7b (Ollama) | Good | ~2–3s/row | Medium | Yes | Change model name |
| Aya Expanse 8b (Ollama) | **Excellent** | ~2–3s/row | Low-Medium | Yes | Change model name |
| Qwen2.5:7b (Ollama) | Good | ~1–2s/row | Low | Yes | Change model name |
| phi3.5:mini (Ollama) | Moderate | ~0.5s/row | Medium | Yes | Change model name |
| E3-JSI/gliner-multi-pii-domains-v1 | Moderate | ~50ms/row | **None** | Yes | Add to code |
| Heuristic flagging + human review | N/A | instant | **None** | Yes | Write regex rules |
| Fine-tuned custom model | **Excellent** | ~50ms/row | **None** | Yes | Requires training data |

---

### Option details

#### `aya-expanse:8b` — new default, multilingual Ollama option
- Drop-in, works via `.env` configuration.
- 8B params: ~5.2B RAM in GPU, excelente Dutch performance.
- Dutch: reasonable but not specifically trained on Dutch PII
- Hallucination risk: will sometimes identify things not in the text (mitigated by the `entity in text` guard already in the code)

#### `mistral:7b` — solid general multilingual
- Strong European language support including Dutch
- JSON mode supported, well-tested for extraction tasks
- Same Ollama setup, just `OLLAMA_MODEL=mistral:7b`
- Slightly better instruction following than llama3.2 on structured output tasks

#### `Aya Expanse 8b` — best multilingual LLM option for Dutch
- Built by Cohere specifically for multilingual performance across 23 languages including **Dutch**
- Outperforms llama3.1:8b and mistral:7b on non-English tasks in published benchmarks
- Available via Ollama: `ollama pull aya-expanse:8b`
- Same RAM requirement as llama3.1:8b (~6–8GB), similar speed
- Best choice if you keep an LLM layer and Dutch quality is the priority

#### `Qwen2.5:7b` — fast, low hallucination
- Alibaba model, strong on structured extraction tasks (JSON output)
- Known for being conservative — less likely to hallucinate entities
- Good multilingual including European languages, though Dutch is not a primary focus
- Available via Ollama: `ollama pull qwen2.5:7b`

#### `phi3.5:mini` (3.8b) — fastest LLM option
- Microsoft's small model, optimized for instruction following
- Very fast on CPU (~0.5s/row), small RAM footprint (~3GB)
- Dutch quality is weaker than the 7–8b models
- Good if speed is the priority and Dutch indirect PII coverage can be partial

#### `E3-JSI/gliner-multi-pii-domains-v1` — deterministic, no hallucination
- GLiNER-based model, Dutch is explicitly in the training data
- Prompt-driven: you define entity labels at runtime — can specify `"physical descriptor"`, `"role description"`, `"implicit person reference"`
- Zero hallucination (span extraction only — if it's not in the text, it won't be returned)
- ~50ms/row on CPU
- Trained on only ~1,487 synthetic examples — smaller training set than the LLM options, so may miss subtle cases
- Best choice if determinism and auditability matter more than maximum recall

#### Heuristic flagging + human review
Flag rows for human review if they contain patterns like:
- Physical adjectives near role words: `(kaal|baard|bril|jas|groot|klein|dik|dun)` near `(docent|mentor|medewerker|leraar|man|vrouw)`
- Implicit role references: `mijn mentor`, `de enige`, `de vrouw die`, `de man die`
- Superlatives: `de grootste`, `de enige`, `de oudste`

This is cheap, deterministic, and explainable to a DPO. No LLM needed. A human reviews only the flagged rows (typically a small percentage of total).

---

## Proposed new architecture

```
Raw text
    │
    ▼
[Layer 1: Presidio]
    - Structured PII: email, phone, student numbers, regex
    - NLP: nl_core_news_lg + en_core_web_lg
    │
    ▼
[Layer 2: tabularisai/eu-pii-safeguard]
    - Named entity PII Presidio missed
    - 42 entity types, all EU languages, XLM-RoBERTa-large
    - Deterministic, no hallucination, fast (~50ms/row)
    │
    ▼
[Layer 3: choose one]
    Option 1: Aya Expanse 8b (Ollama)     — best Dutch LLM, automated, imperfect
    Option 2: mistral:7b (Ollama)         — good multilingual, solid JSON extraction
    Option 3: Qwen2.5:7b (Ollama)         — fast, low hallucination risk
    Option 4: phi3.5:mini (Ollama)        — fastest, weaker Dutch
    Option 5: llama3.2:3b (Ollama)        — current setup, smallest
    Option 6: E3-JSI/gliner-multi-pii-v1  — deterministic, no hallucination, Dutch in training
    Option 7: Heuristic flagging          — deterministic, human reviews flagged rows
    Option 8: Drop entirely               — accept that indirect PII requires manual review
    │
    ▼
Anonymized output (+/- human review queue)
```

---

## Open questions to discuss

1. **Is fully automated indirect PII detection a hard requirement?**
   If not, heuristic flagging + human review is more reliable and explainable.

2. **Is there a HuggingFace model that specifically detects indirect/quasi-identifier PII?**
   This was not yet researched — worth investigating. The ai4privacy dataset may include
   categories like AGE, GENDER, PHYSICAL_ATTRIBUTE that are quasi-identifiers.

3. **License constraint on piiranha-v1 (CC-BY-NC-ND 4.0)**
   If this is a university research project, non-commercial may be fine. Confirm.

4. **Do we need to fine-tune a model on our own data?**
   Using the LLM output as training data (human-reviewed and corrected) to fine-tune
   a Dutch NER model is the long-term industrial path.

5. **Docker setup**
   Adding eu-pii-safeguard requires adding `transformers` + `torch` to requirements.txt
   and a HuggingFace cache volume. The Ollama container can be removed if the LLM
   layer is dropped, simplifying the setup significantly.

---

## Speed comparison (estimated, CPU, 500 rows)

| Architecture | Estimated time |
|---|---|
| Current (Presidio + llama3.1:8b) | ~30–45 min |
| Presidio + eu-pii-safeguard + Aya Expanse 8b | ~8–15 min |
| Presidio + eu-pii-safeguard + mistral:7b | ~5–10 min |
| Presidio + eu-pii-safeguard + Qwen2.5:7b | ~4–8 min |
| Presidio + eu-pii-safeguard + llama3.2:3b | ~5–10 min |
| Presidio + eu-pii-safeguard + phi3.5:mini | ~2–4 min |
| Presidio + eu-pii-safeguard + E3-JSI GLiNER | ~1–2 min |
| Presidio + eu-pii-safeguard only | ~1–2 min |
| Presidio + eu-pii-safeguard + heuristic flagging | ~1–2 min |
