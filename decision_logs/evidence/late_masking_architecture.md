# Evidence — Late Masking Architectuur

**Hoort bij:** Decision Log Entry #3 — Late masking vs. sequentieel masken  
**Stappen.md:** stap 37 en 40  
**Commits:** `677a168` (late masking), `df1640e` (tekst-normalisatie)  
**Datum:** 2026-04-22

---

## Architectuurvergelijking

### Oud — sequentieel masken

```
Originele tekst
      │
      ▼
  [Layer 1 — Presidio]
  detecteert + maskeert direct
      │
      ▼
  Gemaskerde tekst  ← L2 mist context rondom [NAME], [LOCATION]
      │
      ▼
  [Layer 2 — EU-PII-Safeguard]
  detecteert + maskeert op gemaskerde tekst
      │
      ▼
  Output
```

**Probleem:** Als L1 `"Smith"` al heeft vervangen door `[NAME]`, ziet L2 de zin als `"Docent [NAME] gaf les op [LOCATION]"`. De transformer verliest de lexicale context rondom de gemaskerde positie — namen vlak naast andere entiteiten worden daardoor vaker gemist.

---

### Nieuw — late masking (span-collectie)

```
Originele tekst (ongemaskerd)
      │
      ├─────────────────────────┐
      ▼                         ▼
[Layer 1 — Presidio]     [Layer 2 — EU-PII-Safeguard]
collect_presidio_spans()  eu_pii_collect_batch()
retourneert (start,end,tag)  retourneert (start,end,tag)
      │                         │
      └──────────┬──────────────┘
                 ▼
         Spans samenvoegen
         + overlap-resolutie
         (langste span wint)
                 │
                 ▼
         apply_all_masks()
         rechts-naar-links
                 │
                 ▼
             Output
```

**Voordeel:** Beide lagen analyseren de volledige originele tekst. L2-transformer heeft de volledige lexicale context bij elk token.

---

## Ontwerpkeuzes en redenering

### Langste span wint (overlap-resolutie)

Als L1 `"Smith"` detecteert (len=5) en L2 `"docent Smith"` detecteert (len=12), wint de langste span: `"docent Smith"` wordt als één entiteit gemaskerd. Dit is consistent met hoe Presidio intern overlappende recognizers oplost.

### Rechts-naar-links vervangen

Bij het toepassen van spans op een string verschuift elke vervanging de indices van alles ervoor. Door van rechts naar links te vervangen blijven de eerder berekende offsets voor posities vóór de huidige vervanging altijd geldig — geen aparte offset-tracking nodig.

### Lengte-bewarende NER-normalisatie (`normalize_for_ner`)

Vóór NER-analyse wordt de tekst genormaliseerd:

| Patroon | Voor | Na | Lengteverandering |
|---|---|---|---|
| Possessive `'s` | `Smith's` | `Smith  ` | Geen (apostrofe + s → 2 spaties) |
| ALLCAPS naam | `JANSEN` | `Jansen` | Geen |
| Naam tussen quotes | `"Jansen"` | ` Jansen ` | Geen |

**Waarom lengte-bewarend?** De normalisatie wordt toegepast op de tekst die naar de NER-modellen gaat, maar de spans worden daarna toegepast op de **originele** tekst. Als de normalisatie de lengte zou wijzigen, zouden de span-offsets niet meer kloppen op de originele string. Dit is een harde vereiste van het ontwerp, geen optimalisatie.

---

## Implementatie — kernfuncties

| Functie | Bestand | Wat het doet |
|---|---|---|
| `collect_presidio_spans(text, config)` | `layer1_presidio.py` | Analyseert via Presidio, retourneert spans zonder te masken |
| `eu_pii_collect_batch(texts, config)` | `layer2_eu_pii.py` | Batch-NER via HF-pipeline, retourneert spans zonder te masken |
| `normalize_for_ner(text)` | `layer2_text_norm.py` | Lengte-bewarende pre-processing voor NER-invoer |
| `apply_all_masks(text, spans)` | `privacy_agent.py` | Overlap-resolutie + rechts-naar-links maskering |

---

## Recall-meting voor/na

> Meting vóór late masking staat in `LAYER1_IMPROVEMENT_EVIDENCE.md`.  
> Meting ná late masking: recall check output in de UI na commit `677a168` op `test_dataset_v2.csv`.
