# Decision Log - Privacy Officer Agent

**Naam:** Nick van Hooff
**Klas:** MA-AAI1
**Rol:** GenAI Engineer

---

## Entry #6: Parquet of CSV als invoerformaat voor de anonimiseringspipeline?

### Onderzoeksvraag

> Levert Parquet een meetbare snelheidswinst op ten opzichte van CSV bij een dataset van ~15.000 rijen, en blijft de recall gelijk ongeacht het invoerformaat?

---

### 1. Context

**Project:** Privacy Officer Agent, Groepsproject Fontys Semester 4

**Waarom dit nu belangrijk is:**
De pipeline moet ~15.000 rijen verwerken. De vraag was of Parquet als invoerformaat de I/O-bottleneck vermindert en of de recall stabiel blijft ongeacht het formaat.

**Aangetoonde leeruitkomsten:**

- [x] LO1: Analyseren — vergelijkende meting CSV vs Parquet op laadtijd, geheugen en pipelinetijd
- [x] LO2: Adviseren — aanbeveling Parquet boven ~1.000 rijen onderbouwd met meetresultaten (sectie 3 + Conclusie)
- [x] LO3: Ontwerpen — bewuste formaaткeuze op basis van meting op realistische schaal
- [x] LO4: Realiseren — Parquet ondersteuning geïmplementeerd naast CSV
- [ ] LO5: Beheren & Controleren
- [ ] LO6: Persoonlijk Leiderschap
- [x] LO7: Professionele Standaard — groepsgenoot betrokken als tweede meetpunt

---

### 2. Succescriteria

| Criterium                                     | Doel                                                                                                                   |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **Parquet is sneller op realistische schaal** | Gemiddelde pipelinetijd Parquet < CSV bij ~15.000 rijen , verschil ≥5%                                                 |
| **Recall blijft gelijk ongeacht formaat**     | Recall-score op testset (15.000 rijen) is identiek voor CSV en Parquet invoer — geen verschil in anonimiseringsuitkomst   |
| **Resultaat bevestigd door groepsgenoot**     | Groepsgenoot meet op zijn pipeline (embedding model) ook lagere pipelinetijd voor Parquet dan CSV, op dezelfde dataset |

---

### 3. Wat ik heb besloten

**Gekozen: Parquet als aanbevolen invoerformaat, CSV blijft ondersteund**

Parquet laadt sneller, gebruikt minder geheugen, en is 38% kleiner op dezelfde data. Op 15.000 rijen is dat relevant. CSV blijft beschikbaar voor gebruiksgemak (Excel-exports, Google Sheets). De recall-check bevestigde dat beide formaten identieke uitvoer produceren.

---

### 4. Hoe ik dit heb onderzocht (DOT-framework)

**Lab — 6 gecontroleerde runs (privacy pipeline, 15.000 rijen):**
Zes runs met één variabele per stap: inputformaat (CSV vs Parquet) en actieve lagen (L1 only, L2 only, L1+L2). Zelfde dataset, batch size 512, recall objectief gemeten via Python-check. Tijden afgelezen uit outputbestandsnamen. → [laag_benchmark_15000.md](./evidence/laag_benchmark_15000.md)

**Veldonderzoek — groepsgenoot (embedding pipeline, 999 items):**
Groepsgenoot heeft op zijn eigen pipeline dezelfde CSV vs Parquet vergelijking gedaan — onafhankelijk tweede meetpunt op een andere architectuur. → [parquet_vs_csv_benchmark.md](./evidence/parquet_vs_csv_benchmark.md)

---

### 5. Wat ik heb gevonden

**Lab — privacy pipeline (15.000 rijen):**

| Lagen | CSV | Parquet | Verschil |
|-------|-----|---------|---------|
| L1 only | 243s | 230s | −5% |
| L2 only | 135s | 135s | 0% |
| L1+L2 | 394s | 365s | −7% |

Recall identiek voor alle combinaties: L1=78%, L2=68%, L1+L2=85% — ongeacht inputformaat. → [laag_benchmark_15000.md](./evidence/laag_benchmark_15000.md)

**Veldonderzoek — groepsgenoot (999 items, embedding pipeline):**

Parquet beter op alle drie de metrics: −38% bestandsgrootte, −6% pipelinetijd, −2% geheugen. → [parquet_vs_csv_benchmark.md](./evidence/parquet_vs_csv_benchmark.md)

De bottleneck van de privacy-pipeline zit in ML-inferentie (Layer 1/2), niet in I/O. Parquet scheelt meer naarmate de dataset groter is.

---

### 6. Voldoet dit aan mijn criteria?

| Criterium | Doel | Resultaat | Gehaald? |
| --------- | ---- | --------- | -------- |
| **Parquet sneller op realistische schaal** | ≥5% sneller bij ~15.000 rijen | L1: −5%, L1+L2: −7% (L2: 0%) | ✅ |
| **Recall gelijk ongeacht formaat** | Identieke recall CSV vs Parquet op 15.000 rijen | L1=78%, L2=68%, L1+L2=85% voor beide formaten | ✅ |
| **Bevestigd door groepsgenoot** | Lagere pipelinetijd Parquet op zijn pipeline | −6% pipelinetijd, −38% bestandsgrootte, −2% geheugen (999 items) | ✅ |

---

### Conclusie

Alle drie de criteria zijn gehaald op basis van directe meting. Parquet is 5–7% sneller bij laag-intensieve operaties (L1), gelijk bij transformer-inferentie (L2 — bottleneck zit in het model, niet in I/O), en levert identieke recall op als CSV. Het groepsgenootmeetpunt bevestigt het patroon op een andere architectuur. Parquet is de aanbevolen keuze voor datasets boven ~1.000 rijen; CSV blijft beschikbaar voor gebruiksgemak.

---

### 7. Aannames

- De groepsmeting is gedaan op een kleinere dataset (999 items); het absolute verschil bij 15.000 rijen is groter.
- Bij datasets kleiner dan ~1.000 rijen is het verschil verwaarloosbaar.

---

### 8. Bronnen

**(1)** Apache Parquet. (z.d.). *Parquet file format*. [https://parquet.apache.org/](https://parquet.apache.org/)

**(2)** pandas. (z.d.). *pandas.read_parquet*. [https://pandas.pydata.org/docs/reference/api/pandas.read_parquet.html](https://pandas.pydata.org/docs/reference/api/pandas.read_parquet.html)

---

### 9. Implementatiebewijs

| Wat                                          | Bewijs                                                                                                                                         |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| CSV vs Parquet laadtijd analyse              | Stap 27 in [stappen.md](https://github.com/nickvanhooff/agents/blob/main/privacy_officer/stappen.md)                                           |
| Parquet als invoerformaat (`data_loader.py`) | Stap 30 in [stappen.md](https://github.com/nickvanhooff/agents/blob/main/privacy_officer/stappen.md)                                           |
| Kolomdetectie voor CSV en Parquet            | Stap 34 in [stappen.md](https://github.com/nickvanhooff/agents/blob/main/privacy_officer/stappen.md) — `read_headers()`, `/api/detect-columns` |
| Code implementatie                           | [Commit `b690c58`](https://github.com/nickvanhooff/agents/commit/b690c58)                                                                      |
| 6 benchmark runs toegevoegd (CSV + Parquet)  | [Commit `e498452`](https://github.com/nickvanhooff/agents/commit/e498452) — outputbestanden alle lagen                                         |
| Screenshot Claude Code prompt als bewijs     | [Commit `55bbd9c`](https://github.com/nickvanhooff/agents/commit/55bbd9c) — realisatie evidence gedocumenteerd                                 |
| Laagbenchmark evidence (15.000 rijen)        | [laag_benchmark_15000.md](./evidence/laag_benchmark_15000.md)                                                                                  |
| Benchmark groepsgenoot                       | [parquet_vs_csv_benchmark.md](./evidence/parquet_vs_csv_benchmark.md)                                                                          |

---

### 10. Wat dit oplevert

Pipeline ondersteunt nu CSV en Parquet als invoer. Voor de verwachte schaal (~15.000 rijen) is Parquet de aanbevolen keuze — snellere I/O, minder geheugen, kleinere bestanden.
