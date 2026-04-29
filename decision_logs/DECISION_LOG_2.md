# Decision Log - Privacy Officer Agent

**Naam:** Nick van Hooff
**Klas:** MA-AAI1
**Rol:** GenAI Engineer

---

## Entry #2: Throughput-optimalisatie — hoe verwerk ik 676 rijen in minder dan 15 minuten?

### Onderzoeksvraag

> Welke combinatie van `batch_size` en `OLLAMA_NUM_PARALLEL` geeft de beste verwerkingstijd op een laptop met een RTX 4050 (6 GB VRAM), zonder dat de output-kwaliteit achteruitgaat?

---

### 1. Context

**Project:** Privacy Officer Agent, Groepsproject Fontys Semester 4

**Waarom dit nu belangrijk is:**
In DL1 heb ik als criterium gezet: 500 rijen verwerken in maximaal 15 minuten. Toen ik de eerste echte run deed op 676 rijen kostte het ~30 minuten. Dat is twee keer te langzaam. Het systeem draait dus wel, maar is nog niet bruikbaar voor dagelijks gebruik.

De vertraging zat volledig bij Layer 3 — het LLM (Ollama). Ik moest uitvinden hoe ik de LLM-verwerking sneller kon maken zonder van model te wisselen.

**Huidige LO-fase:**
- [x] Analyseren
- [x] Adviseren
- [ ] Ontwerpen
- [x] Realiseren
- [x] Beheren & Controleren

---

### 2. Succescriteria

| Criterium | Doel |
|---|---|
| **Verwerkingstijd** | ≤ 15 min voor 500 rijen (uit DL1) |
| **Output-kwaliteit** | De output van batch 2 en batch 15 mogen maximaal 5% van de rijen inhoudelijk van elkaar verschillen |
| **Stabiliteit** | Geen crashes of timeouts bij de gekozen instelling |

---

### 3. Wat ik heb besloten

**Gekozen instelling: `batch_size=15` in de app + `OLLAMA_NUM_PARALLEL=15` op de server**

Dit bracht de verwerkingstijd van ~30 minuten terug naar ~15 minuten op 676 rijen. De output-kwaliteit bleef goed: de enige verschillen zaten in gevallen waar het antwoord sowieso niet zwart-wit is, zoals of een gebouwnaam PII is of niet. Gestructureerde PII (namen, e-mails, studentnummers) was in beide runs identiek geanonimiseerd.

**Waarom dit werkt:**
`batch_size` bepaalt hoeveel verzoeken de app tegelijk naar Ollama stuurt. `OLLAMA_NUM_PARALLEL` bepaalt hoeveel van die verzoeken de server ook echt tegelijk verwerkt. Als `OLLAMA_NUM_PARALLEL` lager is dan `batch_size`, zet Ollama de extra verzoeken gewoon in de wachtrij — je hebt er dan niets aan. Die twee moeten altijd op elkaar afgestemd zijn.

---

### 4. Hoe ik dit heb onderzocht (DOT-framework)

**Meten (Lab):** `OLLAMA_NUM_PARALLEL` gevarieerd (5, 10, 15) op een kleine dataset. Daarna batch=2 vergeleken met batch=15 op de volledige 676-rijen dataset. Tijd gemeten via Docker-logtijdstempels.

**Output vergelijken (Showroom):** De twee output-bestanden (batch 2 en batch 15) heb ik met Gemini vergeleken om te zien of de grotere batch ook slechtere PII-detectie gaf [1]. De volledige analyse inclusief mijn prompts staat in de evidence.

---

### 5. Wat ik heb gevonden

De details staan in [evidence/batch_parallel_benchmark.md](./evidence/batch_parallel_benchmark.md).

Kort samengevat:
- batch=2 + parallel=1 (de baseline): ~30 minuten voor 676 rijen
- batch=15 + parallel=15: ~15 minuten voor 676 rijen — twee keer zo snel
- Op een kleine testset was parallel=10 iets sneller dan parallel=15; bij de grote dataset was dit verschil verwaarloosbaar
- Gemini vond ~37 rijen met een inhoudelijk verschil (5,5% van 675). Dat is nét boven mijn grens van 5%, maar geen enkel geval was een gemiste naam, e-mail of studentnummer — het zat allemaal in grijze zones

**Kanttekening:** de Gemini-analyse is oriënterend. Ik heb zelf niet rij voor rij gecontroleerd of de conclusie klopt. Voor een harde uitspraak over outputkwaliteit zou ik een formele recall-meting nodig hebben op beide outputs [1].

---

### 6. Voldoet dit aan mijn criteria?

| Criterium | Doel | Resultaat | Gehaald? |
|---|---|---|---|
| **Verwerkingstijd** | ≤ 15 min voor 500 rijen | ~15 min voor 676 rijen | ✅ |
| **Output-kwaliteit** | ≤ 5% afwijking | ~5,5% — maar geen harde PII gemist | 🟡 Deels |
| **Stabiliteit** | Geen crashes | Geen errors aangetroffen | ✅ |

---

### 7. Aannames

- De Gemini-analyse is een hulpmiddel, geen formele meting. De "37 afwijkende rijen" is een schatting van Gemini op basis van de twee CSV-bestanden.
- `OLLAMA_NUM_PARALLEL=15` werkt stabiel op de RTX 4050 met Gemma-4. Als iemand een zwaarder model of kleinere GPU gebruikt, is dit mogelijk te hoog en zal ik moeten terugzetten naar 8–10.
- Ik heb geen VRAM-gebruik exact gemeten — alleen via de GPU-grafiek in Taakbeheer gekeken.

---

### 8. Bronnen

**(1)** Google. (2026, 4 april). *Outputvergelijking batch 2 vs. batch 15*. Gemini-gespreksexport.
https://gemini.google.com/share/84d4aa954d0f
Gebruikte prompts staan in stap 13 van stappen.md.

**(2)** Ollama. (z.d.). *FAQ — How do I configure Ollama server?*. GitHub.
https://github.com/ollama/ollama/blob/main/docs/faq.md

---

### 9. Implementatiebewijs

| Wat | Bewijs |
|---|---|
| Wall time grote dataset | Docker-logs `privacy-agent`: start 15:56, klaar 16:11 — 15 minuten (stap 12 in stappen.md) |
| Parallel actief in container | `docker compose exec ollama env \| grep OLLAMA_NUM` → `OLLAMA_NUM_PARALLEL=15` |
| Batch size in code | Commit `677a168` — `PIPELINE_BATCH_SIZE` env-var in `app.py` |
| Uitgewerkte benchmark | [evidence/batch_parallel_benchmark.md](./evidence/batch_parallel_benchmark.md) |

**Stap in stappen.md:** stap 12 en 13

---

### 10. Wat dit oplevert

**Volgende LO-fase:** Beheren & Controleren

Het systeem haalt nu de 15-minutengrens. Als Layer 3 uitstaat (alleen L1+L2) kan ik `PIPELINE_BATCH_SIZE` nog verder verhogen — dat is relevant voor de 15.000-rijenpilot waarbij Layer 3 waarschijnlijk te langzaam is.

Ik weet nog niet of de 5,5% outputverschil een echt probleem is. Daarvoor moet ik beide outputs formeel testen op dezelfde gelabelde testset. Dat heb ik nog niet gedaan.
