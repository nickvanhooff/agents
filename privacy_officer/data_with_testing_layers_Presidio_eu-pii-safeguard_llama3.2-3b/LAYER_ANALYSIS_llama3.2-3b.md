# Layer 3 vs All Layers – Llama 3.2 3B

Analysis of the anonymization quality and speed for **Llama 3.2 3B** on `safe_student_feedback - extreme.csv` (13 rows), with:
- **Only Layer 3 enabled** (LLM only)
- **All layers enabled** (Presidio + EU-PII-Safeguard + LLM)

Measured runtimes (from your runs):

| Config | Layers | Total time (13 rows) | Approx. per row |
|--------|--------|----------------------|------------------|
| **LLM only** | Layer 3 | **≈ 28 s** | ≈ 2.2 s/row |
| **All layers** | 1 + 2 + 3 | **≈ 30 s** | ≈ 2.3 s/row |

Conclusion on speed: **Presidio + EU‑PII on top of Llama 3.2 3B adds almost no extra time** on your GPU (difference ~2 seconds on 13 rows). So for this model, you basically get the extra safety of layers 1+2 “for free”.

---

## Pipeline Overview (same architecture, different LLM)

| Layer | Technology | Role |
|-------|------------|------|
| **Layer 1** | Microsoft Presidio (Spacy NER + regex) | Deterministic PII and NER for names, locations, phones, emails, usernames, rooms, etc. |
| **Layer 2** | EU-PII-Safeguard | Extra PII/NER (medical like ADHD, some names/locations Presidio misses). |
| **Layer 3** | Llama 3.2 3B (Ollama) | Contextual PII: physical descriptors, roles/titles, courses, indirect references. |

This folder compares **only**:
- `safe_student_feedback - extreme_only_layer3_lama3.2-8b.csv`  → **Layer 3 only**
- `safe_student_feedback - extreme_all_layers_with_llama3.2_3b.csv` → **All layers**

---

## Row-by-Row Highlights (quality differences)

Below: key differences between **LLM-only** and **All layers**.  
Left = `only_layer3` (LLM only), right = `all_layers` (1+2+3).

### Row 1 – Kale docent, rode bril, gebouw R1

- **LLM only:** `[NAME]` + `[NAME]` (role + name merged), `[PHYSICAL_DESCRIPTOR]` for “rode bril”, `[LOCATION]` for R1 but loses the clear “gebouw” structure.
- **All layers:** Presidio first normalizes `Meneer de vriess` and `gebouw R1` (`[NAME]`, `[PII]`), then Llama 3.2 3B adds `[PHYSICAL_DESCRIPTOR]` and `[TITLE]` more consistently.

**Effect:** All layers give a slightly cleaner separation between **name/title/physical/location**, while LLM-only confuses some roles.

### Row 2 – Roos, Jasmijn, blauwe Porsche

- **LLM only:** `Roos`/`Jasmijn` → `[NAME]`, but “blauwe Porsche” becomes `[LOCATION]e [LOCATION]` (double-tag glitch).
- **All layers:** Names get caught earlier; LLM then turns “blauwe Porsche” into `[TITLE]` instead of `[LOCATION]` (still not ideal, but no `[LOCATION]e` artefact).

**Effect:** Both configs mis-handle “Porsche”, but the **double-tag bug** only appears in LLM-only.

### Row 3 – Spelled-out phone + obfuscated email

- **LLM only:** `mentor bereiken via [PII], ... mailen naar [PII]` → LLM does catch both phone and email.
- **All layers:** Presidio + EU‑PII already convert the spelled-out email/phone to `[PII]`, LLM only adds “mijn mentor” → `[NAME]` more reliably.

**Effect:** For **structured PII**, layers 1+2 are safer and deterministic; Llama 3.2 3B does an okay job here, but there is no speed benefit to skip layers 1+2.

### Row 4 – ADHD, rolstoel, Berlijn, Van den Heuvel

- **LLM only:** ADHD is **kept**, Berlijn → `[LOCATION]`, “dhr. Van den Heuvel” → `[TITLE] [NAME]`.
- **All layers:** EU‑PII marks ADHD → `[PII]`, Presidio/EU‑PII also stabilize the location and name before LLM.

**Effect:** If you want **medical info (ADHD) removed**, you need **Layer 2**. LLM-only keeps it.

### Row 5 – Tilburg-Noord, hoofddoek, meneer Pietersen

- **LLM only:** Tilburg-Noord → `[LOCATION]`, “meneer Pietersen” → `[TITLE] [NAME]`, but “Ramadan” → `[LOCATION]` (over-anonymization).
- **All layers:** Similar, but the earlier layers make Tilburg-Noord more stable; still, both configs treat “Ramadan” inconsistently.

**Effect:** Layers 1+2 don’t fully solve the “Ramadan” classification, but they **avoid double `[LOCATION][LOCATION]` artefacts** you sometimes see in LLM-only outputs.

### Row 6 – @tech_guru_040, j_doe88

- **LLM only:** `@tech_guru_040` → `[PII]` with a weird `[LOCATION]` around “op insta”, but leaves `j_doe88` plain.
- **All layers:** Presidio/EU‑PII replace both `@tech_guru_040` and `j_doe88` deterministically with `[PII]`; LLM then sometimes relabels roles (`leraar`) as `[NAME]` but **all handles are safely anonymized**.

**Effect:** For **usernames/handles**, all layers are clearly safer and more consistent.

### Row 7 – Lange jongen, tatoeage, J.D.

- **LLM only:** Good at physical descriptors: “lange” and “nek” get `[PHYSICAL_DESCRIPTOR]`, `J.D.` → `[NAME]`.
- **All layers:** Similar pattern, but some role words get normalized earlier, and semester/course mentions are sometimes turned into `[COURSE/DEPT]`.

**Effect:** Quality is comparable, but All layers reduce the chance of missed names (if spelling is odd).

### Row 8 – “mevrouw de jong”

- **Both configs:** Keep “mevrouw de jong” literal in the string that feeds the model, but LLM converts it into `[NAME]` in the output.

**Effect:** LLM is doing the heavy lifting here; layers 1+2 do not catch this case on their own in other experiments, but they don’t hurt.

### Row 9 – ASML, Sjaak, phone number

- **Both configs:** ASML → `[LOCATION]` (in All), Sjaak → `[NAME]`, phone → `[PII]`. Differences here are minor; All layers are slightly more stable on the location tag.

### Row 10 – Docent p. janssen, piet jansen, BSN-nummers, TQ 3.14

- **LLM only:** “[TITLE] (niet te verwarren met [TITLE]) ... BSN-nummers ... lokaal [LOCATION]` – loses explicit teacher names but keeps BSN literal.
- **All layers:** BSN-nummers stay literal too (no custom BSN recognizer), but room TQ 3.14 and teacher names are handled better because Presidio kicks in first.

### Rows 11–13 – Physical descriptors, pietre, grote schoenen

- **Both configs:** Llama 3.2 3B is doing almost all work here (physical descriptors, typos like “pietre”, etc.).  
  All layers mainly add a bit of stability but don’t change the core behaviour.

---

## Summary: Llama 3.2 3B – Layer 3 vs All Layers

**Speed**
- **LLM only:** ~28 s for 13 rows.
- **All layers (1+2+3):** ~30 s for 13 rows.
- **Conclusion:** On your GPU, **Presidio + EU‑PII are “free” in terms of runtime**; the LLM dominates anyway.

**Quality**
- **LLM only**:
  - Pros: Picks up many contextual PII cases (physical descriptors, “mevrouw de jong”).
  - Cons: More glitches (double tags, wrong labels like `[LOCATION]e [LOCATION]`, keeps ADHD, sometimes leaves usernames).
- **All layers**:
  - Pros: More stable for **structured PII** (handles, emails, phones, many names); removes ADHD; avoids some double-tag artefacts; keeps usernames/emails clearly as `[PII]`.
  - Cons: Still some over-anonymization (e.g. “Ramadan”) and odd tag choices, but overall **strictly better** than LLM-only for privacy, at almost no extra cost.

**Practical advice for Llama 3.2 3B**
- **Use “all layers” as default**: you pay almost no extra time but gain safety and stability.
- Only consider **LLM-only** for debugging Layer 3 behaviour; it is **not** recommended for real anonymization workloads.

*Generated from `data_with_testing_layers_Presidio_eu-pii-safeguard_llama3.2-3b/` test runs (only two configs: LLM-only and All layers).*

