# Decision Log - Privacy Officer Agent

**Naam:** Nick van Hooff
**Klas:** MA-AAI1
**Rol:** GenAI Engineer

---

## Entry #3: Op welk moment moet de tekst gemaskerd worden — tijdens of na de detectie?

### Onderzoeksvraag

> Levert het masken van PII ná alle detectiestappen (in plaats van tussendoor) een hogere recall op — en wat is de impact op precision en F1-score?

---

### 1. Context

**Project:** Privacy Officer Agent, Groepsproject Fontys Semester 4

**Waarom dit nu belangrijk is:**
In de oorspronkelijke pipeline maskeert Layer 1 de naam meteen zodra hij die vindt. Layer 2 (de transformer) ontvangt dan al een tekst waar een stuk uitgehaald is, bijvoorbeeld `"Docent [NAME] gaf les op [LOCATION]"`. Die lege plekken verstoren de context voor de transformer — hij weet niet meer wat er stond en kan daardoor namen die vlakbij een al gemaskerde plek staan vaker missen.

Dit is een architectuurprobleem. De modellen zelf zijn goed genoeg — de volgorde van maskeren schaadt de recall.

**Begrippen (eerder gedefinieerd in DL1 en de begrippenlijst):**
- **Recall** — welk percentage van alle PII in de tekst is gevonden. Dit is de meest kritische maatstaf: één gemist e-mailadres kan al een AVG-overtreding zijn.
- **Precision** — welk percentage van wat het systeem als PII heeft gemarkeerd ook echt PII is. Te lage precision betekent dat er te veel weggehaald wordt wat geen PII is, waardoor de output onleesbaar wordt.
- **F1-score** — een gecombineerde score van recall en precision in één getal. Zie DL1 begrippenlijst voor de volledige uitleg.

**Huidige LO-fase:**
- [x] Analyseren
- [x] Adviseren
- [x] Ontwerpen
- [x] Realiseren
- [ ] Beheren & Controleren

---

### 2. Succescriteria

| Criterium | Doel |
|---|---|
| **Recall** | ≥ 90% op test_dataset_v2 met L1+L2 (SC-1 uit DL1) |
| **Precision** | Geen duidelijke toename van vals alarm ten opzichte van de vorige aanpak |
| **Correctheid** | De gemaskerde tekst moet kloppen — geen verschoven of half-vervangen woorden |

---

### 3. Wat ik heb besloten

**Gekozen: masken aan het einde — Layer 1 en Layer 2 detecteren allebei op de originele tekst, daarna wordt er in één stap gemaskerd**

Layer 1 en Layer 2 kijken allebei naar de ongemaskerde tekst en geven terug waar ze PII hebben gevonden (begin- en eindpositie + label). Die lijsten worden samengevoegd. Als twee detecties overlappen, wint de langste — `"docent Smith"` heeft voorrang op alleen `"Smith"`. Daarna worden alle vervangingen van rechts naar links doorgevoerd in de tekst.

Layer 3 (LLM) staat standaard uit en werkt los van dit systeem.

**Waarom rechts naar links?** Als je een woord ergens halverwege de tekst vervangt, verschuiven alle posities daarna. Door van achter naar voren te werken blijven de posities vóór de huidige vervanging altijd kloppen.

**Extra: lengte-bewarende normalisatie**
Vóór de detectie wordt de tekst eerst genormaliseerd: possessief `'s` (`Smith's` → `Smith  `), ALLCAPS-namen (`JANSEN` → `Jansen`) en namen tussen aanhalingstekens worden aangepast zodat NER-modellen ze beter herkennen. Deze normalisatie mag de lengte van de tekst **niet** veranderen — want de gevonden posities worden daarna op de originele tekst losgelaten, niet op de genormaliseerde versie. Als de lengte wél zou veranderen, zouden alle posities verkeerd zijn.

---

### 4. Hoe ik dit heb onderzocht (DOT-framework)

**Architectuuranalyse (Library):** De twee aanpakken uitgewerkt en vergeleken op het punt waar context verloren gaat [1][2]. Zie [evidence/late_masking_architecture.md](./evidence/late_masking_architecture.md) voor het diagram.

**Testen (Lab):** Na het bouwen getest op test_dataset_v2 (100 rijen, gelabelde PII) via de ingebouwde recall check in de UI. De meting vóór deze wijziging staat in `LAYER1_IMPROVEMENT_EVIDENCE.md`.

---

### 5. Wat ik heb gevonden

De architectuurvergelijking en de keuzes staan uitgewerkt in [evidence/late_masking_architecture.md](./evidence/late_masking_architecture.md).

**Wat ik nog niet weet:** ik heb de recall nog niet formeel gemeten vóór én ná deze wijziging op dezelfde testset. De verwachting is een verbetering van 1–3% — maar dat is een inschatting, geen gemeten resultaat. Die meting staat nog open.

---

### 6. Voldoet dit aan mijn criteria?

| Criterium | Doel | Resultaat | Gehaald? |
|---|---|---|---|
| **Recall** | ≥ 90% op L1+L2 | Nog niet formeel gemeten vóór/na | ❓ Onbekend |
| **Precision** | Geen duidelijke toename vals alarm | Handmatig geen toename gezien, geen formele meting | 🟡 Deels |
| **Correctheid** | Geen verschoven woorden | Handmatig gecontroleerd op test_dataset_v2, geen problemen gevonden | ✅ |

---

### 7. Aannames

- De verwachte recall-winst van 1–3% is een inschatting op basis van redenering, niet gemeten.
- Ik ga er vanuit dat de lengte-bewarende normalisatie werkt voor alle teksten in de testset. Edge cases met bijzondere tekens zijn niet getest.
- Layer 3 is bij deze meting buiten beschouwing gelaten.

---

### 8. Bronnen

**(1)** Microsoft. (z.d.). *Presidio Analyzer Engine — RecognizerResult*. GitHub Pages.
https://microsoft.github.io/presidio/api/analyzer_engine/

**(2)** Hugging Face. (z.d.). *Token Classification Pipeline*. Transformers Docs.
https://huggingface.co/docs/transformers/main_classes/pipelines#transformers.TokenClassificationPipeline

---

### 9. Implementatiebewijs

| Wat | Bewijs |
|---|---|
| Late masking architectuur | Commit [`677a168`](https://github.com/nickvanhooff/agents/commit/677a168) — `apply_all_masks()`, span-collectie per laag |
| Tekst-normalisatie | Commit [`df1640e`](https://github.com/nickvanhooff/agents/commit/df1640e) — `layer2_text_norm.py` |
| Recall-meting vóór | `LAYER1_IMPROVEMENT_EVIDENCE.md` |
| Architectuurdiagram | [evidence/late_masking_architecture.md](./evidence/late_masking_architecture.md) |

**Stap in stappen.md:** stap 37 en 40

---

### 10. Wat dit oplevert

**Volgende LO-fase:** Beheren & Controleren

Nu dit gebouwd is, kan ik een voor/na-meting doen op test_dataset_v2 om te bevestigen of de recall daadwerkelijk verbetert. Dat is de volgende stap. Pas als die meting er is, kan ik dit criterium afvinken.
