# Evidence — Layer 2 Modelkeuze: eu-pii-safeguard vs. openai/privacy-filter

**Hoort bij:** Mogelijke Decision Log — Layer 2 modelkeuze  
**Stappen.md:** stap 41  
**Commits:** `2068050`  
**Datum:** 2026-04-23

---

## Modeloverzicht

| Eigenschap | tabularisai/eu-pii-safeguard | openai/privacy-filter |
|---|---|---|
| **Architectuur** | XLM-RoBERTa-large (0,6B params) | Niet gepubliceerd (token-classification) |
| **Licentie** | Niet gepubliceerd | Apache-2.0 |
| **Trainingsfocus** | 42 PII-types, 26 EU-talen incl. Nederlands | Privacy-filtering (trainingsdata niet publiek) |
| **Zelfgerapporteerde F1** | 97,02% (Precision 97,0%, Recall 97,0%) | Niet gepubliceerd |
| **Entiteitstypes** | Persoonsgegevens, locaties, financieel, medisch | `private_person`, `private_address`, `private_email`, `private_phone`, `private_url`, `private_date`, `account_number`, `secret` |
| **Nederlandse taalondersteuning** | Expliciet (multilingual) | Onbekend |
| **GPU-inferentie** | ✅ via `torch.cuda.is_available()` | ✅ via `torch.cuda.is_available()` |
| **FP16-ondersteuning** | ✅ | ✅ via `LAYER2_FP16` env-var |

---

## Integratie in de pipeline

Beide modellen zijn via dezelfde interface beschikbaar:
- `eu_pii_collect_batch(texts, config)` → `layer2_eu_pii.py`
- `openai_privacy_filter_collect_batch(texts, config)` → `layer2_openai_privacy_filter.py`

Beide retourneren `list[list[(start, end, tag)]]` — directe uitwisselbaarheid in `privacy_agent.py`.

Label-mapping openai/privacy-filter → pipeline-tags:

| Model-label | Pipeline-tag |
|---|---|
| `private_person` | `[NAME]` |
| `private_address` | `[LOCATION]` |
| overig (`private_email`, `private_phone`, etc.) | `[PII]` |

BIOES-prefix stripping (`B-`, `I-`, `E-`, `S-`) is ingebouwd voor labels die het model als `B-private_person` retourneert.

---

## Recall-vergelijking op test_dataset_v2

> **Nog in te vullen** — meting met `openai/privacy-filter` op `test_dataset_v2.csv` (100 rijen, 10 thema's) moet nog worden uitgevoerd.

| Configuratie | Recall | False positives | Opmerking |
|---|---|---|---|
| L1+L2 (eu-pii-safeguard) | zie LAYER1_IMPROVEMENT_EVIDENCE.md | zie LAYER1_IMPROVEMENT_EVIDENCE.md | Baseline |
| L1+L2 (openai/privacy-filter) | — | — | Nog te meten |

**Uitvoeren:**
1. Start Docker stack
2. Upload `test_dataset_v2.csv`, selecteer Layer 1 + Layer 2
3. Kies "Layer 2 model: openai / privacy-filter" in de UI-dropdown
4. Zet "Recall Check" aan, referentiekolom = `voorkomende tekst van pii of indirect wat eruit gehaald moet worden`
5. Noteer recall %, per-thema tabel en false positives

---

## Selectiemogelijkheid in de UI

Dropdown "Layer 2 model" in sectie 2 van de web-UI (standaard `eu-pii-safeguard`):

```
Layer 2: Transformer PII (select model below)
Layer 2 model: [ tabularisai / eu-pii-safeguard ▾ ]
               [ openai / privacy-filter         ]
```

Dropdown is disabled als Layer 2 uitgevinkt is. Model-naam wordt opgenomen in de gegenereerde bestandsnaam voor traceerbaarheid, bijv.: `test_dataset_v2_L12_openai_privacy_filt_b512_47s_recall83.csv`.

---

## Graceful fallback

Als het model niet laadt (download-fout, VRAM-te-vol), retourneert `openai_privacy_filter_collect_batch()` lege spanlijsten — de pipeline crasht niet, Layer 2 wordt effectief overgeslagen.
