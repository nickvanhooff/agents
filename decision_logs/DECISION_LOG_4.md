# Decision Log - Privacy Officer Agent

**Naam:** Nick van Hooff
**Klas:** MA-AAI1
**Rol:** GenAI Engineer

---

## Entry #4: Hoe ontwerp ik testdata en een automatische check om recall en precision te meten?

### Onderzoeksvraag

> Hoe ontwerp ik testdata en een automatische check waarmee ik per run kan zien welke PII gemist is en welke woorden er te veel uitgehaald zijn?

---

### 1. Context

**Project:** Privacy Officer Agent, Groepsproject Fontys Semester 4

**Waarom dit nu belangrijk is:**
Ik had een werkend systeem, maar geen manier om te bewijzen dat het goed werkt. "Het ziet er goed uit" is geen bewijs. Ik had concrete getallen nodig: welk percentage van de PII wordt daadwerkelijk gevonden, en wordt er ook te veel weggehaald? Zonder die meting kan ik geen gefundeerde uitspraken doen over de kwaliteit van de anonimisering.

**Aangetoonde leeruitkomsten:**

- [x] LO1: Analyseren — A/B-test met 4 configuraties, kwantitatieve vergelijking
- [ ] LO2: Adviseren
- [x] LO3: Ontwerpen — ontwerp testdata en check-architectuur (Python vs. LLM keuze, stap 1→6)
- [ ] LO4: Realiseren
- [x] LO5: Beheren & Controleren — geautomatiseerde recall monitoring ingebouwd in de pipeline
- [ ] LO6: Persoonlijk Leiderschap
- [x] LO7: Professionele Standaard — DOT Lab methode expliciet benoemd en verantwoord

---

### 2. Succescriteria


| Criterium                              | Doel                                                                                                                                                                             |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Testdata dekt de juiste gevallen**   | De testdata bevat meerdere PII-types (namen, nummers, e-mails, etages) en meerdere thema's, zodat ik niet alleen het totaal zie maar ook waar het systeem het slechtst presteert |
| **De check maakt geen eigen fouten**   | Als de check zegt dat een woord gevonden is, moet dat kloppen — een foutieve meting is erger dan geen meting                                                                     |
| **Recall per run zichtbaar**           | Na elke run zie ik direct welk percentage PII gevonden is, zonder handmatig te controleren                                                                                       |
| **Gemiste woorden zichtbaar**          | Ik zie welke specifieke woorden zijn blijven staan, zodat ik gericht kan verbeteren                                                                                              |
| **Onverwachte vervangingen zichtbaar** | Ik zie welke woorden er te veel uitgehaald zijn, zodat ik de precision kan beoordelen                                                                                            |
| **Ingebouwd in de UI**                 | De check draait automatisch na een run als ik dat aanzet — niet als apart script                                                                                                 |


---

### 3. Wat ik heb besloten

**Gekozen: Python code voor de check, niet een LLM**

Ik had overwogen om een LLM te gebruiken om te beoordelen of de anonimisering geslaagd was. Maar een LLM hallucineert — hij kan "ja het klopt" zeggen terwijl een woord gewoon nog in de tekst staat. Python code doet dat niet: die checkt letterlijk of een woord nog voorkomt in de geanonimiseerde tekst. Dat is zekerder.

**Hoe de testdata eruitziet:**
Ik heb een gelabeld CSV-bestand gemaakt (`test_dataset_v2.csv`) met 100 rijen verdeeld over 10 thema's. Elke rij heeft:

- Een open antwoord met daarin PII
- Een kolom met de woorden die eruit gehaald moeten worden
- Na de anonimisering: een `true/false` kolom — klopt het dat al die woorden weg zijn?
- Als het `false` is: welke woorden zijn blijven staan?
- En apart: welke woorden zijn er te veel uitgehaald (woorden die geen PII zijn)?

**Hoe de check werkt:**
Python vergelijkt de geanonimiseerde tekst letterlijk met de verwachte PII-woorden. Als een woord nog in de tekst staat, is het gemist — dat is een **false negative**. Als een woord vervangen is dat niet in de verwachte lijst stond, is dat een **onverwachte vervanging** — dat telt mee voor precision.

**Wat er stap voor stap gebouwd is:**

1. Eerst het script los (`check_anonymization.py`) — werkte, maar handmatig draaien is omslachtig
2. Check ingebouwd in de API — draait automatisch na elke anonimisering als je het aanzet
3. Recall percentage zichtbaar in de UI (groen ≥ 90%, oranje ≥ 70%, rood < 70%)
4. Lijst met gemiste woorden zichtbaar in de UI
5. Lijst met onverwachte vervangingen zichtbaar in de UI
6. Per-thema tabel toegevoegd — zo zie ik niet alleen het totaal maar ook waar het systeem het slechts presteert

---

### 4. Hoe ik dit heb onderzocht (DOT-framework)

**Prototyping (Workshop):** Eerst het losse script gebouwd en getest op de testdataset. Daarna stap voor stap in de UI gezet.

**Testen (Lab):** De check uitgevoerd op `test_dataset_v2.csv` met verschillende laagcombinaties. De uitkomsten staan in de evidence.

---

### 5. Wat ik heb gevonden

Vier configuraties getest op `test_dataset_v2.csv` (100 rijen, 10 thema's).


| Configuratie    | Recall | FP-rijen | Indirecte PII gemist | Tijd |
| --------------- | ------ | -------- | -------------------- | ---- |
| Layer 2 only    | 68%    | 2        | 10                   | —    |
| Layer 1 only    | 78%    | 2        | 6                    | 1s   |
| Layer 1 + 2     | 85%    | 4        | 6                    | 4s   |
| Layer 1 + 2 + 3 | 92%    | 70       | 1                    | 304s |


Layer 2 voegt **+7% recall** toe bovenop Layer 1, met slechts 2 extra FP-rijen en 3 seconden extra tijd. Layer 3 haalt de recall op naar 92%, maar duurt 304x langer dan Layer 1 alleen en maskeert 70 rijen te veel — woorden als "docent" (41x) en "mevrouw" (15x) worden onterecht weggehaald, waardoor de tekst context verliest. Layer 1+2 is daarmee de beste balans.

Volledige lijsten met gemiste woorden, FP's per configuratie en screenshots: → [recall_meting_resultaten.md](https://github.com/nickvanhooff/agents/blob/main/decision_logs/evidence/recall_meting_resultaten.md) `@recall_meting_resultaten`

---

### 6. Voldoet dit aan mijn criteria?


| Criterium                    | Doel                           | Gehaald?                 |
| ---------------------------- | ------------------------------ | ------------------------ |
| **Betrouwbaarheid check**    | Python, geen LLM               | ✅ Code checkt letterlijk |
| **Recall zichtbaar**         | % in UI                        | ✅                        |
| **Precision zichtbaar**      | Onverwachte vervangingen in UI | ✅                        |
| **Bruikbaar tijdens testen** | In de UI, niet apart script    | ✅                        |


---

### 7. Aannames

- De testdata (`test_dataset_v2.csv`) is zelf gemaakt en niet afkomstig van echte studentfeedback. De resultaten zijn daardoor een indicatie, geen garantie dat het systeem even goed werkt op echte data.
- De check is case-insensitief — `Smith` en `smith` worden als hetzelfde gezien. Als een woord in een heel andere vorm terugkomt (bijv. een afkorting), mist de check dat.

---

### 8. Bronnen

**(1)** Python Software Foundation. (z.d.). *difflib — Helpers for computing deltas*. Python Docs.
[https://docs.python.org/3/library/difflib.html](https://docs.python.org/3/library/difflib.html)
Gebruikt voor het vinden van onverwachte vervangingen via `SequenceMatcher`.

---

### 9. Implementatiebewijs


| Wat                                                      | Bewijs                                                                         |
| -------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Recall check script | [Commit `cd5eaa4`](https://github.com/nickvanhooff/agents/commit/cd5eaa4) — `check_anonymization.py` |
| Check ingebouwd in API | [Commit `cd5eaa4`](https://github.com/nickvanhooff/agents/commit/cd5eaa4) — `/api/anonymize` met `run_check` parameter |
| UI met recall, gemiste woorden, onverwachte vervangingen | Stap 18, 19 en 24 in stappen.md |
| Testdataset ontwerp | [testdata_ontwerp.md](https://github.com/nickvanhooff/agents/blob/main/decision_logs/evidence/testdata_ontwerp.md) `@testdata_ontwerp` |
| Meetresultaten L1 vs L1+L2 | [recall_meting_resultaten.md](https://github.com/nickvanhooff/agents/blob/main/decision_logs/evidence/recall_meting_resultaten.md) `@recall_meting_resultaten` |
| Resultaat CSV L1 only | [test_dataset_v2_L1_b512_1s_recall78.csv](https://github.com/nickvanhooff/agents/blob/main/decision_logs/evidence/test_dataset_v2_L1_b512_1s_recall78.csv) `@csv_recall_L1` |
| Resultaat CSV L1+L2 | [test_dataset_v2_L12_..._recall85.csv](https://github.com/nickvanhooff/agents/blob/main/decision_logs/evidence/test_dataset_v2_L12_eu_pii_safeguard_b512_4s_recall85%20(1).csv) `@csv_recall_L12` |
| Resultaat CSV L1+L2+L3 | [test_dataset_v2_L123_..._recall92.csv](https://github.com/nickvanhooff/agents/blob/main/decision_logs/evidence/test_dataset_v2_L123_eu_pii_safeguard_gemma4-e4b_b512_304s_recall92.csv) `@csv_recall_L123` |


**Stap in stappen.md:** stap 14, 15, 16, 18, 19, 20 en 24

---

### 10. Wat dit oplevert

**Volgende LO-fase:** Beheren & Controleren

Nu ik de recall kan meten, kan ik elke aanpassing aan de pipeline direct beoordelen op effect. Zonder deze meetmethode was ik blind aan het itereren. De volgende stap is de meting gebruiken om te beslissen welke laagcombinatie het beste werkt voor de echte dataset.