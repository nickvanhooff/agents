# Anonymization Testing Conclusion

Summary of all layer and model tests on `safe_student_feedback - extreme.csv` (13 rows of challenging Dutch/English student feedback).

---

## What each layer does


| Layer                     | Technology               | What it catches                                                                               | What it misses                                                                 |
| ------------------------- | ------------------------ | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| **L1 – Presidio**         | Spacy NER + custom regex | Names, emails, phones, locations, @handles, spelled-out emails, room codes                    | "mevrouw de jong", ADHD, physical descriptors, BSN-nummers                     |
| **L2 – EU-PII-Safeguard** | XLM-RoBERTa transformer  | Medical PII (ADHD), some names L1 misses                                                      | Many Dutch names (Roos, Sjaak, Pietersen), has tokenizer bugs when run alone   |
| **L3 – LLM (Ollama)**     | Aya 8B / Llama 3.2 3B    | Physical descriptors, titles, contextual refs ("mijn mentor"), "mevrouw de jong", BSN-nummers | Spelled-out emails/phones, sometimes over-anonymizes ("semester 4", "project") |


**Key insight:** No single layer catches everything. They complement each other.

---

## Speed comparison (13 rows)


| Config                    | Aya 8B                  | Llama 3.2 3B        |
| ------------------------- | ----------------------- | ------------------- |
| **L1 only (Presidio)**    | ≈ 0.25 s                | ≈ 0.25 s            |
| **L2 only (EU-PII)**      | ≈ 1.4 s                 | ≈ 1.4 s             |
| **L1+L2**                 | ≈ 1.6 s                 | ≈ 1.6 s             |
| **L3 only (LLM)**         | ≈ 1:48 min (~8.3 s/row) | ≈ 28 s (~2.2 s/row) |
| **All layers (L1+L2+L3)** | ≈ 1:41 min (~7.8 s/row) | ≈ 30 s (~2.3 s/row) |


- Presidio and EU-PII are effectively **free** in terms of time.
- The **LLM dominates runtime**. Llama 3.2 3B is ~4× faster than Aya 8B.

---

## Model comparison: Aya 8B vs Llama 3.2 3B


| Aspect                   | Aya 8B                                          | Llama 3.2 3B                              |
| ------------------------ | ----------------------------------------------- | ----------------------------------------- |
| **Dutch quality**        | Better — built for 23 languages including Dutch | Decent but weaker on Dutch nuances        |
| **Speed (all layers)**   | ~7.8 s/row                                      | ~~2.3 s/row (**~~3.4× faster**)           |
| **Tag consistency**      | More consistent (e.g. [PII] for handles)        | More glitches (double tags, wrong labels) |
| **Over-anonymization**   | Some ("digibord", "semester 4")                 | Some ("Ramadan", "mijn accent")           |
| **"mevrouw de jong"**    | Caught                                          | Not caught                                |
| **Physical descriptors** | Caught well                                     | Caught well                               |
| **ADHD (medical)**       | Only via L2                                     | Only via L2                               |


---

## Best configuration

**Always use all layers (L1 + L2 + L3).** Layers 1+2 add almost zero extra time but catch structured PII (emails, phones, handles, ADHD) that the LLM misses or mislabels.


| Priority          | Recommendation                                              |
| ----------------- | ----------------------------------------------------------- |
| **Best privacy**  | All layers + Aya 8B                                         |
| **Best speed**    | All layers + Llama 3.2 3B                                   |
| **Fast + no LLM** | L1+L2 only (misses physical descriptors and contextual PII) |
| **Avoid**         | Any single layer alone — each has blind spots and bugs      |


---

## What only the LLM can do

These PII types are **only caught by the LLM layer** (L3), regardless of model:

- Physical descriptors ("kale docent", "rode bril", "bold", "sweaty")
- Contextual identifiers ("blauwe Porsche", "mijn mentor")
- Names in unusual formats ("mevrouw de jong" — Aya only)
- BSN-nummers (no Presidio regex for this)

Without the LLM, these stay in the output and require **manual review**.

---

## Quick reference: what gets filtered where


| PII type             | L1  | L2  | L3           |
| -------------------- | --- | --- | ------------ |
| Standard names       | ✅   | ⚠️  | ✅            |
| "mevrouw de jong"    | ❌   | ❌   | ✅ (Aya only) |
| Email, phone         | ✅   | ✅   | ✅            |
| Spelled-out email    | ✅   | ❌   | ❌            |
| @handles, usernames  | ✅   | ⚠️  | ⚠️           |
| Locations            | ✅   | ⚠️  | ✅            |
| Room codes           | ✅   | ✅   | ✅            |
| ADHD / medical       | ❌   | ✅   | ❌            |
| Physical descriptors | ❌   | ❌   | ✅            |
| BSN-nummers          | ❌   | ❌   | ✅            |


