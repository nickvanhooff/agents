# Evidence — Batch × Parallel Throughput Benchmark

**Hoort bij:** Decision Log Entry #2 — Throughput-optimalisatie  
**Stappen.md:** stap 12 en 13  
**Datum:** 2026-04-04

---

## Testopstelling

| Parameter | Waarde |
|---|---|
| Hardware | RTX 4050, 6 GB VRAM |
| Model | Gemma-4 via Ollama |
| Dataset | `safe_cleaned_survey_long_format_q(all).csv`, 676 rijen |
| Gemeten via | Docker-logtijdstempels (`privacy-agent` + `ollama`) |

---

## Meting 1 — Effect van OLLAMA_NUM_PARALLEL (kleine dataset, batch_size=15 constant)

| OLLAMA_NUM_PARALLEL | Wall time |
|---|---|
| 5 | ~22 s |
| **10** | **~15–16 s** ← snelst |
| 15 | ~19 s |

---

## Meting 2 — Effect van batch_size (grote dataset, OLLAMA_NUM_PARALLEL=15)

| Configuratie | Wall time (676 rijen) |
|---|---|
| batch=2 (baseline) | ~30 minuten |
| **batch=15** | **~15 minuten** |

Docker-log bewijs: start `15:56`, klaar `16:11` → 15 min wall time.  
Verificatie `OLLAMA_NUM_PARALLEL` actief: `docker compose exec ollama env | grep OLLAMA_NUM` → `OLLAMA_NUM_PARALLEL=15`.

---

## GPU-gedrag (Task Manager, GPU 3D)

| Parallel instelling | GPU-patroon |
|---|---|
| Laag (1–5) | ~40% gemiddeld gebruik, vlak profiel |
| Hoog (15) | Scherpe pieken (burst-achtig) — hogere piekbelasting, lagere totale doorlooptijd |

Burst-patroon bij hoge parallel hoort bij wave-achtige verwerking: GPU kort maximaal belast per wave.

---

## Outputvergelijking batch 2 vs. batch 15

**Methode:** twee export-CSV's vergeleken via Gemini (zie [gesprek](https://gemini.google.com/share/84d4aa954d0f)).  
**Gebruikte prompts (stap 13 in stappen.md):**
> "de 2 csv bestanden met batch size 2 en batch size 15 — komen deze 2 overheen met elkaar?"  
> "er is ollama gebruikt hiervoor. wat zijn de verschillen en wat is betere pii en wat is bruikbaarder"

| Meting | Waarde |
|---|---|
| Totaal rijen vergeleken | 675 |
| Rijen met verschil | ~37 (~5,5%) |
| Gestructureerde PII (naam, e-mail, studentnr.) | Identiek in beide runs |

**Aard van de verschillen (uitsluitend grijze zones):**

| Voorbeeld | Batch 2 | Batch 15 |
|---|---|---|
| "building A–D" | Vaak behouden | Vaker `[LOCATION]` |
| "Tableau / PowerBI" | Tableau als `[NAME]` | PowerBI ook als `[COURSE/DEPT]` |
| Tagsyntax | Soms `[[NAME]]` | Consistent `[NAME]` |
| "thick accent" | Niet gemarkeerd | `[PHYSICAL_DESCRIPTOR]` |

**Conclusie:** batch 15 is agressiever in grijze zones maar consistenter in opmaak. Geen missen van harde PII aangetoond.

---

## Technische verklaring verschillen

Ollama verwerkt parallelle chat-requests (niet dezelfde setup als vLLM continuous batching). De ~37 verschillen zijn plausibel door requestvolgorde en JSON-randgevallen bij gelijktijdige requests.  
De GPU-padding-verklaring die Gemini noemde (tensor-batching, Flash Attention) geldt voor vLLM-stijl batching, niet voor Ollama parallelle chats — dit is een **hypothese van Gemini**, geen bevestigde oorzaak.
