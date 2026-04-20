# Privacy Officer Pipeline — Verbeteringsevidence

**Datum:** 2026-04-20  
**Testdataset:** `test_dataset_v2.csv` — 100 rijen, 10 thema's, gelabelde PII  
**Meetmethode:** Recall check ingebouwd in `/api/anonymize` (stap 18); false positive detectie via `difflib.SequenceMatcher` (stap 19)

---

## Recall progressie Layer 1 only

| Iteratie | Wijziging | Recall | FP-rijen |
|---|---|---|---|
| Baseline (Layer 1+2 samen) | — | **80%** | 20 |
| Layer 1 only — voor fixes | — | **64%** | 18 |
| + FLOOR_REFERENCE regex | `3e etage`, `derde etage` vangen | *(meegenomen in volgende meting)* | — |
| + DUTCH_PHONE regex | `06-XXXXXXXX` vangen | **69%** | 23 |
| + DUTCH_HONORIFIC regex | `Mevrouw/Meneer/heer → [TITLE]` | **69%** | 23* |

\* FP-teller steeg van 18 naar 23: de regex vangt meer honorific-instanties dan spaCy NER deed. Dit is gewenst gedrag — honorifics worden nu correct als `[TITLE]` geanonimiseerd. De testdataset labelt ze niet als verwachte PII, waardoor ze als "extra" worden meegeteld.

---

## Per-thema recall (Layer 1 only — na fixes)

| Thema | Score | Recall | Extra (FP) |
|---|---|---|---|
| Insufficient contact hours | 9/10 | **90%** | +1 |
| Poor teacher communication | 9/10 | **90%** | +5 |
| Technology & online resources | 9/10 | **90%** | +1 |
| Unclear assessment criteria | 7/10 | **70%** | +1 |
| Workload & time management | 7/10 | **70%** | +2 |
| Slow grading by Smith | 6/10 | **60%** | +1 |
| Teaching style & explanation quality | 6/10 | **60%** | +5 |
| Course depth & quality | 6/10 | **60%** | +3 |
| Diversity & inclusivity | 5/10 | **50%** | +2 |
| Student support & teacher availability | 5/10 | **50%** | +2 |

**Zwakste thema's:** Diversity & inclusivity en Student support — bevatten de meeste gezondheids- en fysieke descriptoren (Art. 9 AVG), die structureel buiten het bereik van regex/NER vallen.

---

## Wat Layer 1 nu vangt (na alle fixes)

| Entiteit | Methode | Tag |
|---|---|---|
| Persoonsnamen | spaCy NER (`PERSON`) | `[NAME]` |
| Nationaliteit/religie/politiek | spaCy NER (`NRP`) | `[NAME]` |
| E-mailadressen | Presidio built-in | `[PII]` |
| Telefoonnummers (generiek) | Presidio built-in | `[PII]` |
| **NL mobiel `06-XXXXXXXX`** | Custom regex `DUTCH_PHONE` | `[PII]` |
| Studentnummers (5–7 cijfer) | Custom regex `STUDENT_NUMBER` | `[PII]` |
| Gebruikersnamen / @handles | Custom regex `USERNAME` | `[PII]` |
| Obfuscated e-mail (NL gespeld) | Custom regex `OBFUSCATED_EMAIL` | `[PII]` |
| Gebouw-/zaalcodes (R1, TQ 3.14) | Custom regex `BUILDING_OR_ROOM` | `[PII]` |
| **Etage-aanduidingen** | Custom regex `FLOOR_REFERENCE` | `[LOCATION]` |
| Locaties / steden | spaCy NER (`LOCATION`) | `[LOCATION]` |
| **Nederlandse postcode** | Custom regex `DUTCH_POSTCODE` | `[LOCATION]` |
| BSN / burgerservicenummer | Custom regex `NL_BSN` | `[PII]` |
| **Honorifics (Mevrouw/Meneer/heer)** | Custom regex `DUTCH_HONORIFIC` | `[TITLE]` |

**Vet** = toegevoegd tijdens deze sessie (2026-04-20).

---

## Resterende false negatives na Layer 1 fixes

### Namen gemist door spaCy NER
`Prins` (3x), `De Vries` (2x), `Smith` (1x), `Vermeer` (1x), `Groot` (1x), `Bos` (1x), `Thompson` (1x), `Bakker` (1x), `De Boer` (1x)

**Oorzaak:** spaCy NER mist namen zonder context of korte enkelvoudige achternamen. Niet oplosbaar met regex zonder grote false positive risico.  
**Fix:** Layer 3 (LLM).

### Bijzondere persoonsgegevens (Art. 9 AVG)
`ADHD` (2x), `dyslexie` (1x), `depressie` (1x), `autisme` (1x), `burnout` (1x), `diabetes` (1x), `slechthorend` (1x), `visuele beperking` (1x), `motorische beperking` (1x)

**Oorzaak:** Woordenschat-gebaseerde PII — hetzelfde woord kan context-afhankelijk wel of geen PII zijn. Regex geeft te veel false positives.  
**Fix:** Layer 3 (LLM).

### Fysieke/indirecte descriptoren
`rolstoelgebruiker` (2x), `kale docent` (1x), `lange man met bril` (1x), `korte blonde haren` (1x), `hoofddoek` (1x), `vooraan zit` (1x), `de baard` (1x)

**Oorzaak:** Meerdere woorden, semantisch — geen vaste vorm.  
**Fix:** Layer 3 (LLM).

### Verdachte studentnummers (zou gevangen moeten zijn)
`1234567` (1x), `876543` (1x), `234567` (1x)

**Oorzaak:** Vermoedelijk onderdeel van een e-mailadres in de brondata (bijv. `1234567@student.fontys.nl`) — `EMAIL_ADDRESS` consumeert de hele string, waarna `STUDENT_NUMBER` het getal niet apart matcht.  
**Verificatie:** Controleer in de brondata of deze nummers standalone staan of in een e-mail.

---

---

## Meting: alle lagen samen (L1 + L2 + L3)

**Datum:** 2026-04-20

### Recall per thema

| Thema | Score | Recall | Extra (FP) |
|---|---|---|---|
| Course depth & quality | 10/10 | **100%** | +9 |
| Poor teacher communication | 10/10 | **100%** | +8 |
| Slow grading by Smith | 10/10 | **100%** | +4 |
| Technology & online resources | 10/10 | **100%** | +6 |
| Unclear assessment criteria | 10/10 | **100%** | +5 |
| Insufficient contact hours | 9/10 | **90%** | +4 |
| Workload & time management | 9/10 | **90%** | +7 |
| Diversity & inclusivity | 8/10 | **80%** | +9 |
| Teaching style & explanation quality | 8/10 | **80%** | +9 |
| Student support & teacher availability | 7/10 | **70%** | +9 |

**Totaal: 91% recall (91/100), 70 rijen met onverwachte vervangingen**

### Resterende false negatives (9 rijen)

| Waarde | Categorie | Oorzaak |
|---|---|---|
| `rolstoelgebruiker` (2x) | Fysiek/indirect | LLM mist ook in context |
| `visuele beperking` (1x) | Gezondheid Art. 9 | LLM mist |
| `motorische beperking` (1x) | Gezondheid Art. 9 | LLM mist |
| `slechthorend` (1x) | Gezondheid Art. 9 | LLM mist |
| `burnout` (1x) | Gezondheid Art. 9 | LLM mist |
| `diabetes` (1x) | Gezondheid Art. 9 | LLM mist |
| `vooraan zit` (1x) | Fysiek/indirect | Te impliciet voor LLM |
| `Groot` (1x) | Naam | NER + LLM missen beide |

### False positives analyse (70 rijen)

De dominante bron is Layer 3 (LLM) dat `docent` / `Docent` als titel aanmerkt:

| Waarde | Aantal | Bron | Analyse |
|---|---|---|---|
| `Docent` | 25x | Layer 3 | LLM tagt generiek functiewoord als [TITLE] |
| `docent` | 16x | Layer 3 | Idem, kleine letter |
| `Mevrouw` | 9x | Layer 1 | Correct [TITLE], maar niet in testlabels |
| `mevrouw` | 6x | Layer 1 | Idem |
| `Meneer` | 4x | Layer 1 | Idem |
| `meneer` | 2x | Layer 1 | Idem |
| `(studentnummer` | 2x | Layer 1/2 | Regex matcht getal met haakje in de tekst |
| `docenten` | 1x | Layer 3 | Meervoud meegeslepen door LLM |
| `professor` / `Professor` | 1x+1x | Layer 3 | Functiewoord als titel |
| `Teacher` | 1x | Layer 3 | Idem (Engels) |
| `Software` / `Engineering` | 1x+1x | Layer 2/3 | Vakterm als entiteit |
| `grote` / `collegezaal.` | 1x+1x | Layer 3 | Duidelijke overmatch |
| `Communicatie` / `Nederlandstalige` | 1x+1x | Layer 2/3 | Overmatch |

**Kernprobleem:** Layer 3 (LLM) gebruikt `docent` als bewijs dat er een specifieke persoon wordt bedoeld, terwijl het vaak een generiek functiewoord is. De LLM-prompt moet scherper aangeven dat generieke functiewoorden **zonder naam** niet als PII gelden.

---

## Vergelijking alle configuraties

| Configuratie | Recall | FP-rijen | Observatie |
|---|---|---|---|
| Layer 1+2 (voor L1 fixes) | 80% | 20 | Baseline sessie |
| Layer 1 only (voor fixes) | 64% | 18 | Structureel plafond regex/NER |
| Layer 2 only | 63% | 3 | Weinig FP, maar mist vaste patronen |
| Layer 1 only (na fixes) | **69%** | 23 | +5% door phone + honorifics |
| **Alle lagen (L1+L2+L3)** | **91%** | 70 | Beste recall; FP door LLM over-tagging `docent` |

### Conclusie

De triple-layer pipeline haalt **91% recall** op de testdataset — boven de SC-1 drempel van 90%. De 9 resterende false negatives zijn gezondheids- en fysieke descriptoren die ook voor de LLM te impliciet zijn.

Het grootste verbeterpunt is nu de **false positive rate**: 70 rijen door Layer 3 over-tagging van `docent`/`professor`/`Teacher` als titel. Dit is een **prompt-issue** in `get_dynamic_prompt()` — de definitie van `titles` moet scherper: alleen honorifics **direct voor een naam**, niet standalone functiewoorden.

**Layer 1 alone: 69% recall** — Layer 1 is de snelste, meest deterministische laag en dekt alle structureel herkenbare PII. Voor gezondheidsdata (Art. 9 AVG) en fysieke descriptoren is Layer 3 essentieel.
