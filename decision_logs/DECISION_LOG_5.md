# Decision Log - Privacy Officer Agent

**Naam:** Nick van Hooff
**Klas:** MA-AAI1
**Rol:** GenAI Engineer

---

## Entry #5: Layer 3 uitzetten — weegt de hogere recall op tegen de false positives?

### Onderzoeksvraag

> Layer 3 verhoogt de recall maar introduceert veel false positives. Weegt die hogere recall op tegen de slechtere leesbaarheid van de output — gegeven dat de data lokaal blijft?

---

### 1. Context

**Project:** Privacy Officer Agent, Groepsproject Fontys Semester 4

**Waarom dit nu belangrijk is:**
Layer 3 was oorspronkelijk bedoeld voor de moeilijkste gevallen: indirecte PII zoals fysieke beschrijvingen en omschrijvingen die geen NER-model pikt. Maar tijdens het meten bleek dat Layer 3 ook veel te veel weghaalde — generieke woorden als "docent" werden als PII gemarkeerd, terwijl dat geen naam of persoonsgebonden informatie is. Dat verlaagt de bruikbaarheid van de output. Tegelijkertijd besloten we in een overleg dat de data sowieso lokaal blijft — er is geen extern risico als een enkele indirecte beschrijving blijft staan.

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
| **Leesbaarheid van de output** | Docenten moeten de geanonimiseerde feedback nog kunnen analyseren — te veel weggehaalde woorden maakt dat onmogelijk |
| **AVG-risico** | Acceptabel gezien de context — data blijft lokaal, intern gebruik |

---

### 3. Wat ik heb besloten

**Besloten in overleg: Layer 3 wordt standaard uitgeschakeld**

Layer 3 haalt te veel weg wat geen PII is. Een woord als "docent" is geen persoonsgebonden informatie — maar het LLM markeerde het stelselmatig als `[TITLE]`. Dat maakt de feedback minder leesbaar en verlaagt de bruikbaarheid voor de eindgebruiker.

De data blijft lokaal opgeslagen en wordt alleen intern gebruikt. Dat betekent dat het risico van een gemiste indirecte beschrijving (zoals "de lange man met bril") acceptabel is — het gaat niet naar buiten.

Layer 1 en Layer 2 vangen de harde PII (namen, e-mails, studentnummers, telefoonnummers) betrouwbaar op. Dat is het meest kritische deel.

Layer 3 blijft in de code staan en kan via de UI weer aangezet worden. De beslissing is niet definitief — als de use case verandert (bijv. als de data toch gedeeld wordt buiten de organisatie) moet de afweging opnieuw gemaakt worden.

---

### 4. Hoe ik dit heb onderzocht (DOT-framework)

**Meten (Lab):** Recall en false positives gemeten met Layer 3 aan en uit op `test_dataset_v2.csv`. De false positive analyse liet zien dat "docent" de grootste bron van onnodige vervangingen was — 41 keer als `[TITLE]` gemarkeerd terwijl er geen naam bij stond.

**Overleg (Field research):** Beslissing genomen in groepsoverleg op basis van de meetresultaten en de context dat de data lokaal blijft.

---

### 5. Wat ik heb gevonden

→ *Voeg hier de recall/precision vergelijking L1+2 vs. L1+2+3 toe als evidence.*

Kort samengevat (details in `LAYER1_IMPROVEMENT_EVIDENCE.md`):

| Configuratie | Recall | Onverwachte vervangingen |
|---|---|---|
| L1 + L2 | zie evidence | zie evidence |
| L1 + L2 + L3 | 91% | ~70 — waarvan 41x "docent" als [TITLE] |

De 91% recall met alle lagen klinkt goed, maar de 70 false positives maken de output aanzienlijk minder bruikbaar. L1+L2 zonder die vervuiling geeft een schonere analyse.

---

### 6. Voldoet dit aan mijn criteria?

| Criterium | Doel | Gehaald? |
|---|---|---|
| **Leesbaarheid van de output** | Leesbare output zonder onnodige vervangingen | ✅ Zonder L3 geen "docent"-vervangingen |
| **AVG-risico** | Acceptabel — data blijft lokaal | ✅ Bevestigd in overleg |

---

### 7. Aannames

- De beslissing dat het AVG-risico acceptabel is, is genomen op basis van de huidige use case: lokale verwerking, intern gebruik. Als de data buiten de organisatie gaat, verandert deze afweging.
- "Docent" als false positive is een prompt engineering-probleem, geen fundamenteel probleem met Layer 3. Met een betere prompt zou Layer 3 mogelijk bruikbaarder zijn — maar dat is nog niet onderzocht.

---

### 8. Bronnen

**(1)** Autoriteit Persoonsgegevens. (z.d.). *Wat zijn persoonsgegevens?*
https://www.autoriteitpersoonsgegevens.nl/themas/basis-avg/privacy-en-persoonsgegevens/wat-zijn-persoonsgegevens
Gebruikt als referentie voor wat wel en niet als PII telt onder de AVG.

---

### 9. Implementatiebewijs

| Wat | Bewijs |
|---|---|
| Layer 3 standaard uitgevinkt in UI | Commit `677a168` — `index.html` Layer 3 checkbox standaard uit |
| False positive analyse Layer 3 | `LAYER1_IMPROVEMENT_EVIDENCE.md` — sectie all-layers resultaten |

**Stap in stappen.md:** stap 14 (succescriteria) en overleg beslissing

---

### 10. Wat dit oplevert

**Volgende LO-fase:** Beheren & Controleren

Met Layer 3 uit is de pipeline sneller en de output schoner. De recall gaat wel omlaag — Layer 3 pikt indirecte beschrijvingen op die L1+L2 missen. Maar die lagere recall is een bewuste afweging: de data blijft lokaal en de leesbaarheid van de output weegt zwaarder dan de extra vangst van Layer 3. Als er een situatie ontstaat waarbij indirecte beschrijvingen toch kritisch zijn, kan Layer 3 via de UI worden aangezet — de code staat er nog in.
