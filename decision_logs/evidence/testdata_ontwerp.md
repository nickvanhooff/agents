# Evidence — Ontwerp testdata voor recall- en precisionmeting

**Hoort bij:** Decision Log Entry #4 — Hoe ontwerp ik testdata en een automatische check?  
**Stappen.md:** stap 15 en 16  
**Datum:** 2026-04-15

---

## Waarom een eigen testdataset?

Om recall en precision te meten heb je data nodig waarbij je van tevoren weet welke woorden eruit gehaald moeten worden. Echte studentfeedback heeft dat niet — die is niet gelabeld. Ik heb daarom zelf een testdataset gemaakt met nep-feedback waar de PII-woorden per rij zijn opgeschreven.

---

## Structuur van test_dataset_v2.csv

Het bestand heeft 100 rijen, verdeeld over 10 thema's (10 rijen per thema).

| Kolom | Inhoud | Waarom |
|---|---|---|
| `thema's` | Onderwerp van de feedback (bijv. "Poor teacher communication") | Zodat ik per thema kan zien waar het systeem het slechtst presteert |
| `voorkomende tekst van pii of indirect wat eruit gehaald moet worden` | De letterlijke woorden die gevonden moeten worden, bijv. `naam:Smith, email:j.smith@fontys.nl` | Dit is de ground truth waar de check tegenaan vergelijkt |
| `open antwoord` | De nep-feedbackzin in het Nederlands of Engels | Dit is de tekst die door de anonimisering gaat |

Na de anonimisering voegt de check twee extra kolommen toe:
- `geanonimiseerd` — `True` als alle verwachte woorden weg zijn, `False` als er nog iets staat
- `gemiste_pii` — welke woorden zijn blijven staan
- `extra_geanonimiseerd` — welke woorden er te veel uitgehaald zijn

---

## De 10 thema's

| Thema | Wat erin zit |
|---|---|
| Slow grading by Smith | Namen van docenten, e-mailadressen |
| Insufficient contact hours | Lokaal- en etage-aanduidingen |
| Course depth & quality | Vaknamen, studentnummers |
| Unclear assessment criteria | Namen, studentnummers |
| Poor teacher communication | E-mails, telefoonnummers |
| Teaching style & explanation quality | Namen, fysieke beschrijvingen |
| Workload & time management | Studentnummers, etages |
| Student support & teacher availability | Namen, gebouwaanduidingen |
| Technology & online resources | Gebruikersnamen, e-mails |
| Diversity & inclusivity | Fysieke beschrijvingen, indirecte identificatoren |

---

## Verdeling van PII-types

| Type | Aantal rijen |
|---|---|
| Naam | 73 |
| Gebouw / lokaal / etage | 15 |
| Indirect fysiek (bijv. "kale docent") | 15 |
| Studentnummer | 13 |
| E-mailadres | 8 |
| Gebruikersnaam | 3 |
| Telefoonnummer | 2 |
| Verborgen e-mail (bijv. "x punt y apenstaartje...") | 1 |

Namen komen het vaakst voor omdat dat de meest voorkomende PII is in studentfeedback. Fysieke beschrijvingen en etage-aanduidingen zijn bewust meegenomen omdat die door Layer 1+2 structureel gemist worden — ze zijn nodig om de grens van de pipeline zichtbaar te maken.

---

## Ontwerpkeuze: waarom pipe-formaat met type:waarde

De gelabelde kolom gebruikt het formaat `naam:Smith, email:j.smith@fontys.nl`. Dit maakt het mogelijk om programmatisch te splitsen op `,` en `:` en zo per PII-waarde te checken of die nog in de geanonimiseerde tekst staat.

Een vrij tekstveld zoals "de naam Smith en zijn e-mailadres" zou handmatige parsing vereisen en daardoor fouten introduceren in de meting zelf.

---

## Validatie van de testdata

Elk woord in de gelabelde kolom staat letterlijk in de bijbehorende feedbackzin. Dit is gecontroleerd bij het aanmaken van het bestand (`build_test_dataset.py`). Als een woord niet letterlijk in de zin staat, klopt de check niet — want de check zoekt ook letterlijk.

---

## Resultaten

De meetresultaten op deze testdata staan in `LAYER1_IMPROVEMENT_EVIDENCE.md`.
