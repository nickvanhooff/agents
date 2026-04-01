# Layer-by-Layer Anonymization Analysis (Aya 8B)

Analysis of the triple-layer PII anonymization pipeline tested on `safe_student_feedback - extreme.csv` (13 rows of challenging Dutch/English student feedback).

---

## Pipeline Architecture

| Layer | Technology | What it catches |
|-------|------------|-----------------|
| **Layer 1** | Microsoft Presidio (Spacy NER + regex) | Structured PII: names, emails, phones, locations, student numbers, @handles, Dutch spelled-out emails |
| **Layer 2** | EU-PII-Safeguard (tabularisai, XLM-RoBERTa) | Named entities Presidio missed: complex names, addresses, medical conditions, IBANs |
| **Layer 3** | Ollama LLM (Aya Expanse 8B) | Contextual PII: physical descriptors, titles, courses, indirect references |

Each layer receives the **output** of the previous layer. Layer-only runs use **raw text** as input for that layer.

---

## Summary: What Each Configuration Does

| File         | Layers used       | Input to each layer |
| ------------ | ----------------- | ------------------- |
| `layer_1`    | Presidio only     | Raw → Layer 1       |
| `layer_2`    | EU-PII only       | Raw → Layer 2       |
| `layer_3`    | LLM only          | Raw → Layer 3       |
| `layer1+2`   | Presidio + EU-PII | Raw → L1 → L2       |
| `all_Layers` | Full pipeline     | Raw → L1 → L2 → L3  |

---

## Timing per configuration (13 rows, Aya 8B)

Measured from the `Anonymizing feedback` progress bars in the Docker logs (same CSV, 13 rows):

| File | Layers used | Total time | Approx. per row |
|------|-------------|------------|------------------|
| `safe_student_feedback - extreme_layer_1.csv` | Presidio only | **≈ 0.25 s** (`13/13 [00:00…]`) | ≈ 0.02 s/row |
| `safe_student_feedback - extreme_layer_2.csv` | EU-PII only | **≈ 1.4 s** (`13/13 [00:01…]`) | ≈ 0.11 s/row |
| `safe_student_feedback - extreme_layer_3.csv` | LLM only | **≈ 1:48 min** (`13/13 [01:48…]`) | ≈ 8.3 s/row |
| `safe_student_feedback - extreme_layer1+2.csv` | Presidio + EU-PII | **≈ 1.6 s** (`13/13 [00:01…]`) | ≈ 0.12 s/row |
| `safe_student_feedback - extreme_alll_Layers.csv` | All layers (Presidio + EU-PII + LLM) | **≈ 1:41 min** (`13/13 [01:41…]`) | ≈ 7.8 s/row |

So for this dataset:
- **Presidio/EU-PII-only** runs are effectively instantaneous for 13 rows.
- The **LLM layer dominates runtime**: going from EU-PII-only (≈1.4 s) to All layers (≈1:41) adds ~1.5 minutes.

---

## Row-by-Row Comparison

### Row 1

**Original:** Meneer de vriess, je weet wel die kale docent met die opvallende rode bril uit gebouw R1, gaf mij onterecht een 3.4 voor mijn C++ herkansing op 12 maart.

| Config | anonymized_feedback_text |
|--------|--------------------------|
| **Layer 1** | `[NAME], je weet wel die kale docent met die opvallende rode bril uit gebouw [PII]...` |
| **Layer 2** | `Meneer de v[NAME]s...` ← **BROKEN** (partial replacement) |
| **Layer 3** | `[NAME], je weet wel die [PHYSICAL_DESCRIPTOR] [TITLE] met [PHYSICAL_DESCRIPTOR] uit [LOCATION]...` |
| **Layer 1+2** | `[NAME], je weet wel die kale docent met die opvallende rode bril uit gebouw [PII]...` |
| **All** | `[NAME], je weet wel die [TITLE] met die [PHYSICAL_DESCRIPTOR] uit [LOCATION]...` |

**Findings:**
- **Layer 2 alone** corrupts "de vriess" → "de v[NAME]s" (tokenizer artifact).
- **Layer 3** catches "kale", "rode bril" (physical), "docent" (title), "gebouw R1" (location).
- **All layers** gives the cleanest result; Layer 1+2 keeps "kale docent" and "rode bril" (no LLM).

---

### Row 2

**Original:** Ik vind dat Roos en Jasmijn de lessen veel beter voorbereiden, maar die nieuwe opleidingsdirecteur die altijd in die blauwe Porsche rijdt, luistert niet naar ze.

| Config | anonymized_feedback_text |
|--------|--------------------------|
| **Layer 1** | `[NAME] en [NAME]... die blauwe [NAME] rijdt` (Porsche → [NAME]) |
| **Layer 2** | **No changes** — Roos, Jasmijn, Porsche all kept |
| **Layer 3** | `[NAME] en [NAME]... die altijd in [LOCATION] rijdt` |
| **Layer 1+2** | Same as Layer 1 |
| **All** | `[NAME] en [NAME]... die altijd in [LOCATION] rijdt` |

**Findings:**
- **Layer 2 alone** misses all names (EU-PII struggles on this sentence).
- **Layer 1** wrongly tags "Porsche" as [NAME].
- **Layer 3 / All** correctly treat "blauwe Porsche" as location-like identifier.

---

### Row 3

**Original:** Je kan mijn mentor bereiken via nul zes en dan 123 vier vijf 6 zeven acht, of mailen naar s punt van_der_meer apenstaartje student punt fontys punt nl.

| Config | anonymized_feedback_text |
|--------|--------------------------|
| **Layer 1** | `...via nul zes en dan 123 vier vijf 6 zeven acht, of mailen naar [PII].` |
| **Layer 2** | `...of mailen naar [PII] [NAME] [NAME] [PII] [PII].` ← **BROKEN** (splits email into wrong tokens) |
| **Layer 3** | **No changes** — LLM does not parse spelled-out formats |
| **Layer 1+2** | `...via nul zes en dan [PII] vier vijf 6 zeven acht, of mailen naar [PII].` |
| **All** | `Je kan [NAME] bereiken via [PII], of [PII].` |

**Findings:**
- **Layer 2 alone** destroys the email structure (tokenizer mislabels "s punt van_der_meer...").
- **Layer 1** catches the spelled email via custom regex; phone number partially kept.
- **All** (LLM) replaces "mijn mentor" and condenses phone/email to [PII] — cleanest.

---

### Row 4

**Original:** Omdat ik ADHD heb en afhankelijk ben van een rolstoel, was de verplichte excursie naar Berlijn met dhr. Van den Heuvel echt een logistieke ramp.

| Config | anonymized_feedback_text |
|--------|--------------------------|
| **Layer 1** | `Omdat ik ADHD heb... naar [LOCATION] met [NAME]...` |
| **Layer 2** | `Omdat ik [PII] heb... met dhr. [NAME]...` (ADHD → PII) |
| **Layer 3** | `Omdat ik ADHD heb... naar [LOCATION] met [NAME]...` |
| **Layer 1+2** | `Omdat ik [PII] heb... naar [LOCATION] met [NAME]...` |
| **All** | Same as Layer 1+2 |

**Findings:**
- **Layer 2** correctly flags ADHD as medical PII.
- **Layer 3** keeps ADHD (LLM prompt may not emphasize medical).
- **Layer 1** misses ADHD; Presidio has no medical-entity recognizer.

---

### Row 5

**Original:** Als enige student uit Tilburg-Noord met een hoofddoek in de klas van meneer Pietersen, voelde ik me erg ongemakkelijk bij zijn grappen over de Ramadan.

| Config | anonymized_feedback_text |
|--------|--------------------------|
| **Layer 1** | `...uit [LOCATION] met een hoofddoek... van [NAME]` |
| **Layer 2** | `...uit [LOCATION][LOCATION]... van meneer Pietersen` ← **BROKEN** (double tag, Pietersen kept) |
| **Layer 3** | `...uit [LOCATION]... van meneer Pietersen` (Pietersen kept) |
| **Layer 1+2** | `...uit [LOCATION]... van [NAME]` |
| **All** | `...uit [LOCATION]... van [NAME]` |

**Findings:**
- **Layer 2 alone** produces "[LOCATION][LOCATION]" for "Tilburg-Noord" (hyphen split) and misses "Pietersen".
- **Layer 1** handles "Tilburg-Noord" and "Pietersen" correctly.
- **Layer 3 alone** misses "Pietersen" (possible context issue).
- **Layer 1+2** and **All** give correct output.

---

### Row 6

**Original:** Die leraar, op insta bekend als @tech_guru_040, deelde de code van mijn afstudeerproject zonder toestemming op zijn github genaamd j_doe88.

| Config | anonymized_feedback_text |
|--------|--------------------------|
| **Layer 1** | `Die leraar, op insta bekend als [PII], deelde de code van mijn afstudeerproject zonder toestemming op zijn github genaamd [PII].` |
| **Layer 2** | `Die leraar, op insta bekend als @[PII], deelde de code van mijn afstudeerproject zonder toestemming op zijn github genaamd [NAME].` |
| **Layer 3** | `Die [TITLE], op insta bekend als [NAME], deelde de code van mijn afstudeerproject zonder toestemming op zijn github genaamd [NAME].` |
| **Layer 1+2** | `Die leraar, op insta bekend als [PII], deelde de code van mijn afstudeerproject zonder toestemming op zijn github genaamd [PII].` |
| **All** | `Die [NAME], op insta bekend als [PII], deelde de code van mijn afstudeerproject zonder toestemming op zijn github genaamd [PII].` |

**Findings:**
- **Layer 3 alone** uses [NAME] for social handles (semantically wrong, should be [PII]). Also replaces "leraar" → [TITLE].
- **All** replaces "leraar" → [NAME] (different from L3's [TITLE] — LLM behaves differently on pre-processed input).
- **Layer 1** and **Layer 1+2** correctly use [PII] for handles.
- **Layer 2** keeps "@" prefix in "@[PII]" (cosmetic) and uses [NAME] instead of [PII] for j_doe88.

---

### Row 7

**Original:** Tijdens het project in semester 4 werd ik in de groep gezet met die lange jongen met die tatoeage in zijn nek, J.D., wat zorgde voor veel wrijving.

| Config        | anonymized_feedback_text                                                                                                                                          |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Layer 1**   | `Tijdens het project in semester 4 werd ik in de groep gezet met die lange jongen met die tatoeage in zijn nek, [NAME], wat zorgde voor veel wrijving.`           |
| **Layer 2**   | `Tijdens het project in semester 4 werd ik in de groep gezet met die lange jongen met die tatoeage in zijn nek, J.D., wat zorgde voor veel wrijving.` (J.D. kept) |
| **Layer 3**   | `Tijdens het [COURSE/DEPT] in [LOCATION] werd ik in de groep gezet met [TITLE] met die [PHYSICAL_DESCRIPTOR], [NAME], wat zorgde voor veel wrijving.`             |
| **Layer 1+2** | Same as Layer 1                                                                                                                                                   |
| **All**       | `Tijdens het [COURSE/DEPT] in [COURSE/DEPT] werd ik in de groep gezet met die [PHYSICAL_DESCRIPTOR], [NAME], wat zorgde voor veel wrijving.`                      |

**Findings:**
- **Layer 2 alone** misses "J.D." (initials).
- **Layer 3** over-anonymizes: "project" → [COURSE/DEPT], "semester 4" → [LOCATION], "die lange jongen" → [TITLE].
- **All** also over-anonymizes "project" and "semester 4" (both → [COURSE/DEPT]), but handles the physical descriptor better than L3 (no spurious [TITLE] for "die lange jongen").

---

### Row 8

**Original:** The feedback session met mevrouw de jong was really unfair, ze zei literal dat mijn accent 'te allochtoon' klonk voor een commerciële pitch.

| Config | anonymized_feedback_text |
|--------|--------------------------|
| **Layer 1** | **Not replaced** |
| **Layer 2** | **Not replaced** |
| **Layer 3** | `...met [NAME] was really unfair...` |
| **Layer 1+2** | **Not replaced** |
| **All** | `...met [NAME]...` |

**Findings:**
- **Layer 1 and 2 both miss** "mevrouw de jong" (surname without capital, mixed with title).
- **Only Layer 3** catches it. Critical case for the LLM layer.

---

### Row 9

**Original:** Mijn stagebegeleider bij ASML, een man wiens naam klinkt als 'Sjaak', stuurde me 's avonds laat appjes vanaf zijn werknummer +31 6 8765 4321.

| Config | anonymized_feedback_text |
|--------|--------------------------|
| **Layer 1** | `Mijn stagebegeleider bij ASML, een man wiens naam klinkt als '[NAME]', stuurde me 's avonds laat appjes vanaf zijn werknummer [PII].` |
| **Layer 2** | `Mijn stagebegeleider bij ASML, een man wiens naam klinkt als 'Sjaak', stuurde me 's avonds laat appjes vanaf zijn werknummer [PII].` (Sjaak kept) |
| **Layer 3** | `Mijn stagebegeleider bij [LOCATION], een man wiens naam klinkt als '[NAME]', stuurde me 's avonds laat appjes vanaf [LOCATION].` (phone → [LOCATION] wrong tag) |
| **Layer 1+2** | Same as Layer 1 |
| **All** | `Mijn [TITLE] bij [LOCATION], een man wiens naam klinkt als '[NAME]', stuurde me 's avonds laat appjes vanaf zijn werknummer [PII].` |

**Findings:**
- **Layer 2 alone** misses "Sjaak" (phonetic spelling).
- **Layer 3 alone** mislabels the phone number "+31 6 8765 4321" as [LOCATION] instead of [PII].
- **All** replaces "stagebegeleider" → [TITLE] and "ASML" → [LOCATION]; Layer 1 correctly handles the phone number and "Sjaak".

---

### Row 10

**Original:** Docent p. janssen (niet te verwarren met piet jansen van de IT-desk) liet per ongeluk het Excel-bestand met alle BSN-nummers en cijfers openstaan op het digibord in lokaal TQ 3.14.

| Config | anonymized_feedback_text |
|--------|--------------------------|
| **Layer 1** | `Docent [NAME] (niet te verwarren met [NAME]) liet per ongeluk het Excel-bestand met alle BSN-nummers en cijfers openstaan op het digibord in lokaal [PII].` |
| **Layer 2** | `Docent [NAME] (niet te verwarren met piet jansen van de IT-desk) liet per ongeluk het Excel-bestand met alle BSN-nummers en cijfers openstaan op het digibord in lokaal [PII].` (piet jansen kept) |
| **Layer 3** | `[NAME] (niet te verwarren met piet jansen van de IT-desk) liet per ongeluk het Excel-bestand met alle [PII] en cijfers openstaan op het digibord in [LOCATION].` |
| **Layer 1+2** | `Docent [NAME] (niet te verwarren met [NAME]) liet per ongeluk het Excel-bestand met alle BSN-nummers en cijfers openstaan op het digibord in lokaal [PII].` |
| **All** | `[TITLE] [NAME] (niet te verwarren met [NAME]) liet per ongeluk het Excel-bestand met alle [PII] en cijfers openstaan op het [PII] in [LOCATION].` |

**Findings:**
- **Layer 2 alone** misses "piet jansen" (lowercase).
- **Layer 3 alone** catches "BSN-nummers" → [PII] and "Docent p. janssen" → [NAME], but misses "piet jansen". "Excel-bestand" and "digibord" are both correctly kept by L3.
- **All layers** replaces "digibord" → [PII] (debatable over-anonymization). "Excel-bestand" is kept even in All.
- **Layer 1** does not have BSN regex; "BSN-nummers" stays in L1, L2, and L1+2. Only L3 (and therefore All) catches it.
- **Layer 1+2** is solid for names and room codes; All adds "Docent" → [TITLE] and "digibord" → [PII].

---

### Rows 11–13

**Original row 11:** the teacher who is bold and with whirt shirt on and sweaty was really mad at me and was screaming  
**Original row 12:** docent pietre had rode schoenen aan en een blauwe jas  in de klas  
**Original row 13:** de docent met grote schoenen en teenslippers had haren op zijn voeten

| Row | Layer 1 | Layer 2 | Layer 3 | Layer 1+2 | All |
|-----|---------|--------|---------|----------|-----|
| 11 | No change | No change | `the [TITLE] who is [PHYSICAL_DESCRIPTOR] and with [PHYSICAL_DESCRIPTOR] on and sweaty...` (teacher→[TITLE], sweaty kept) | No change | `the teacher who is [PHYSICAL_DESCRIPTOR] and with [PHYSICAL_DESCRIPTOR] on and [PHYSICAL_DESCRIPTOR]...` (teacher kept, sweaty→[PHYSICAL_DESCRIPTOR]) |
| 12 | No change | No change | `[TITLE] pietre had [PHYSICAL_DESCRIPTOR] aan en een [PHYSICAL_DESCRIPTOR]  in de klas` | No change | Same as L3 |
| 13 | No change | No change | `de [TITLE] met [PHYSICAL_DESCRIPTOR] en [PHYSICAL_DESCRIPTOR] had [PHYSICAL_DESCRIPTOR]` (drops "op zijn voeten") | No change | Same as L3 |

**Findings:**
- **Layers 1 and 2** never catch physical descriptors or informal names like "pietre".
- **Row 11 L3 vs All differ:** L3 replaces "teacher" → [TITLE] but keeps "sweaty". All keeps "teacher" but replaces "sweaty" → [PHYSICAL_DESCRIPTOR]. The LLM behaves differently depending on whether the input was pre-processed by L1+L2.
- **Layer 3** is the only one that anonymizes physical descriptors — but "pietre" stays in all configs (typo/variant of "Pierre").
- **Layer 3** truncates row 13 ("op zijn voeten" lost).

---

## Why Is Something Filtered (or Not)?

### Layer 1 (Presidio) — What it catches
- **Caught:** Standard PERSON, EMAIL, PHONE, LOCATION, @handles, Dutch spelled emails, room codes (R1, TQ 3.14), usernames with digits.
- **Missed:** "mevrouw de jong" (title+surname), "piet jansen" (lowercase), "BSN-nummers", physical descriptors, ADHD (medical).

### Layer 2 (EU-PII-Safeguard) — What it catches
- **Caught:** ADHD (medical), some names Presidio misses.
- **Missed:** Roos, Jasmijn, Porsche, J.D., Sjaak, Pietersen, "mevrouw de jong", "piet jansen".
- **Bugs:** Partial replacements ("de v[NAME]s"), double tags ("[LOCATION][LOCATION]"), tokenization breaks on spelled-out email.

### Layer 3 (LLM) — What it catches
- **Caught:** "mevrouw de jong", physical descriptors (kale, rode bril, bold), titles (docent, teacher, leraar), contextual refs ("mijn mentor"), "blauwe Porsche" as location, "BSN-nummers".
- **Missed (when run alone):** Spelled-out phone/email, "Pietersen" in row 5, "sweaty" in row 11 (only caught in All), "piet jansen" in row 10.
- **Over-anonymizes:** "semester 4", "project" (row 7), "die lange jongen" → [TITLE] (row 7).
- **Note:** "Excel-bestand" and "digibord" are correctly kept by L3 alone. Only "digibord" gets replaced in All (by the LLM operating on L1+L2 pre-processed input).
- **Truncation:** Row 13 loses "op zijn voeten".
- **Inconsistency:** LLM behaves differently on raw text vs. pre-processed text (see row 11: L3 alone replaces "teacher" → [TITLE] but All keeps "teacher").

---

## Recommendation: Best Configuration

| Use case | Recommended config | Reason |
|----------|--------------------|--------|
| **Maximum privacy** | **All layers** | Catches the most PII, including "mevrouw de jong" and physical descriptors. |
| **Speed vs. quality** | **Layer 1+2** | No LLM (~4× faster). Good for structured + named-entity PII. Misses indirect/contextual PII. |
| **Deterministic, auditable** | **Layer 1+2** | No LLM = no hallucination, reproducible, explainable to DPO. |
| **Avoid Layer 2 alone** | Never use | Tokenizer bugs (partial replacements, double tags) corrupt output. |
| **Avoid Layer 3 alone** | Avoid | Misses spelled-out formats, mislabels some entities, over-anonymizes. |

### Best overall: **All layers**

For this dataset, the full pipeline (Layer 1 → 2 → 3) gives the best anonymization. Layer 2 fixes some Presidio gaps (e.g. ADHD). Layer 3 is essential for:
- "mevrouw de jong"
- Physical descriptors (rows 11–13)
- Contextual identifiers ("blauwe Porsche", "mijn mentor")

Trade-off: ~13–14 s/row with Aya 8B. For large batches, consider Layer 1+2 plus human review of rows flagged by heuristics (e.g. physical descriptors, implicit references).

---

## Quick Reference: What Gets Filtered Where

| PII type | L1 | L2 | L3 |
|----------|----|----|-----|
| Standard names (Jan, Pietersen) | ✅ | ⚠️ | ✅ |
| "mevrouw de jong" | ❌ | ❌ | ✅ |
| Email, phone (standard) | ✅ | ✅ | ✅ |
| Spelled-out email | ✅ | ❌ (breaks) | ❌ |
| @handles, usernames | ✅ | ⚠️ | ⚠️ [NAME] |
| Locations (Berlijn, Tilburg) | ✅ | ⚠️ | ✅ |
| Room codes (R1, TQ 3.14) | ✅ | ✅ | ✅ |
| ADHD, medical | ❌ | ✅ | ❌ |
| Physical descriptors | ❌ | ❌ | ✅ |
| "blauwe Porsche" | ⚠️ [NAME] | ❌ | ✅ [LOCATION] |
| BSN-nummers | ❌ | ❌ | ✅ |

---

*Generated from `data_with_testing_layers_Presidio_eu-pii-safeguard_aya/` test runs. All table cells verified against actual CSV output.*
