# Stappenlog — Privacy Officer Agent (LLM-laag & Docker)

Dit document beschrijft stappen en keuzes rond vLLM/Ollama, Docker Compose, timeouts en de LLM-extractieprompt voor de Privacy Officer-agent. Structuur afgestemd op `eva-multi-agent/STAPPEN.md` (zelfde portfolioformaat).

**Datum laatste update:** 2026-04-24 (Stap 42: entity carry-forward — namen uit één rij meenemen naar andere rijen)

**Transparantie — Cursor:** Cursor is gebruikt voor iteratieve code-aanpassingen (compose, timeouts, `parse_llm_json_response`) en voor het opzetten van dit stappenlog in dezelfde vorm als Eva. Keuzes, foutanalyse uit logs en benchmark zijn eigen werk; Cursor versnelt uitwerking en herstructurering, geen vervanging van domeinbeslissingen.

---

## Stap 1: vLLM-quantization en logs begrijpen

**Datum:** 2026-04-04

**Wat is er gedaan:**
- Uitzoeken wat `--dtype auto` vs `--quantization awq_marlin` doet; in logs staan o.a. `quantization=awq_marlin` en `dtype=torch.float16`.
- Compose-command uitbreiden met expliciete `--quantization awq_marlin` voor Qwen2.5-3B-AWQ waar van toepassing.

**Waarom:**
Geen verkeerde aanname dat `dtype auto` al 4-bit quantiseert; voor AWQ is een expliciete quant-flag nodig.

**Bronnen:**
- vLLM-documentatie, eigen compose-logs.

**Zelf bedacht:**
Compose/args afstemmen op wat de logs echt tonen, niet op de kortste interpretatie van `auto`.

---

## Stap 2: Modellen wisselen (Ollama vs vLLM, HF-gated, Qwen-zoektocht)

**Datum:** 2026-04-04

**Wat is er gedaan:**
- Pogingen met `aya-expanse:8b` in vLLM (HF-repo), gated models met `HF_TOKEN`, en Qwen-varianten.
- Focus op **Qwen2.5-3B-Instruct-AWQ** in vLLM voor 6 GB VRAM, naast Ollama-pad met andere tags.

**Waarom:**
vLLM verwacht Hugging Face-model-id’s; Ollama-tags zijn een ander ecosysteem; gated repos vereisen token + toegang op HF.

**Bronnen:**
- Hugging Face model pages, vLLM serve logs.

**Zelf bedacht:**
`.env` met `HF_TOKEN`, `VLLM_MODEL`, `OLLAMA_MODEL`; compose `HUGGING_FACE_HUB_TOKEN` voor vLLM.

---

## Stap 3: vLLM-geheugen en healthcheck (6 GB GPU)

**Datum:** 2026-04-04

**Wat is er gedaan:**
- Aanpassen van `--max-model-len`, `--gpu-memory-utilization`, `--max-num-seqs`.
- Healthcheck `start_period` / `retries` verruimd tegen lange model-load.

**Waarom:**
Fout `No available memory for the cache blocks` en “unhealthy” tijdens opstarten op een kleine GPU.

**Bronnen:**
- vLLM-argumenten, trial-and-error op laptop-GPU.

**Zelf bedacht:**
Conservatieve waarden die op RTX 4050 6 GB passen.

---

## Stap 4: Docker Compose — Ollama bereikbaar en services consistent

**Datum:** 2026-04-04

**Wat is er gedaan:**
- `ollama` niet alleen achter een profile laten staan zonder dat `privacy-agent` start; bij `LLM_BACKEND=ollama` ollama mee starten.
- `depends_on: ollama` met `condition: service_healthy`.
- `OLLAMA_MODEL` doorgeven aan de ollama-service (entrypoint `ollama pull`).
- `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` ook naar **privacy-agent** voor eu-pii-safeguard.

**Waarom:**
Fout `Failed to connect to Ollama` als alleen `privacy-agent` draaide; entrypoint kende `OLLAMA_MODEL` niet → verkeerde pull.

**Bronnen:**
- Docker Compose docs, eigen logs.

**Zelf bedacht:**
Eén stack waarbij Ollama en agent samen kloppen.

---

## Stap 5: Ollama HTTP-timeout (60s) vs zware model-load

**Datum:** 2026-04-04

**Wat is er gedaan:**
- `ollama.Client(..., timeout=OLLAMA_TIMEOUT_SECONDS)` met default **600s**; `OLLAMA_TIMEOUT_SECONDS` in compose.
- `asyncio.wait_for` blijft extra bovengrens op het async-pad.

**Waarom:**
Logs toonden `POST /api/chat` ~**1m0s** en “client connection closed” terwijl het model nog laadde — httpx-default ~60s, niet de `asyncio`-timeout alleen.

**Bronnen:**
- ollama-python (`httpx` in client), Ollama server logs.

**Zelf bedacht:**
Default 600s; batch default **1** om geen twee zware loads tegelijk te triggeren.

---

## Stap 6: GPU vs CPU offload en contextlengte

**Datum:** 2026-04-04

**Wat is er gedaan:**
- `OLLAMA_CONTEXT_LENGTH` (default **2048**) in compose om KV-cache te verkleinen.
- Logs geïnterpreteerd: soms meer lagen op GPU (`KvSize`, `GPULayers`).

**Waarom:**
Op 6 GB past niet alles tegelijk; lagere context kan ruimte vrijmaken voor weights op GPU.

**Bronnen:**
- Ollama server logs (`offloaded X/Y layers`, `KvSize`).

**Zelf bedacht:**
Eventueel 1024 proberen als er nog veel CPU-offload is.

---

## Stap 7: Gemma 4 via Ollama (niet raw Hugging Face URL)

**Datum:** 2026-04-04

**Wat is er gedaan:**
- Afstemmen: **`google/gemma-4-E4B-it` op HF** is niet hetzelfde als het Ollama-model-id; voor Ollama: **`ollama pull gemma4:e4b`** (zie [Google: Run Gemma with Ollama](https://ai.google.dev/gemma/docs/integrations/ollama)).

**Waarom:**
Ollama gebruikt GGUF/library-tags; HF-repo is Transformers-pad.

**Bronnen:**
- Google AI docs, Ollama library.

**Zelf bedacht:**
`.env`: `OLLAMA_MODEL=gemma4:e4b`.

---

## Stap 8: Ollama-image te oud (412)

**Datum:** 2026-04-04

**Wat is er gedaan:**
- Fout `pull model manifest: 412` → nieuwere Ollama-server image.

**Waarom:**
`gemma4`-manifesten vereisen recentere server.

**Bronnen:**
- [ollama.com/download](https://ollama.com/download), `docker compose pull ollama`.

**Zelf bedacht:**
`image: ollama/ollama:latest` + `pull_policy: always` in compose; daarna pull en container opnieuw.

---

## Stap 9: LLM-laag — dynamische JSON-prompt en robuust parsen

**Datum:** 2026-04-04

**Wat is er gedaan:**
- `get_dynamic_prompt(config)` bouwt de system prompt voor laag 3; categorieën worden alleen toegevoegd als de UI-config dat toelaat (`names`, `titles`, `locations`, `courses`, `pii`/`student_nr`, `physical`).
- vLLM: `response_format={"type": "json_object"}`; Ollama: `format="json"`.
- `parse_llm_json_response()`: eerst plain JSON, dan markdown-codeblokken (triple backtick, vaak met `json`-label), dan `JSONDecoder.raw_decode` vanaf eerste `{`.

**Waarom:**
`format="json"` kan nog steeds 200 OK geven met niet-strikt JSON (extra tekst, fences) → `Failed to parse JSON` en `[NEEDS_REVIEW_ERROR]`; vooral gezien bij modellen zoals `gemma4:e4b`.

**Bronnen:**
- Eigen logs met Gemma; Python `json` gedrag.

**Zelf bedacht:**
Centrale parser voor sync- en async-pad in `privacy_agent.py`.

**Prompt — vaste kern (uit code; categorieën zijn dynamisch):**

Zie implementatie: `group/agents/privacy_officer/src/core/privacy_agent.py` — functie `get_dynamic_prompt`.

```
You are a strict data extraction tool. Your ONLY job is to extract identifying entities from the text.
You MUST output ONLY a valid JSON object. Do not output anything else.
The JSON object must contain arrays of exact strings found in the text that match the requested categories.
If no matches are found for a category, return an empty array [] for that key.

=== CATEGORIES TO EXTRACT ===
( dynamisch: per ingeschakelde toggle regels als '- 'names': ...', '- 'titles': ...', enz. )

=== STRICT RULES ===
1. The strings in your JSON arrays MUST be EXACT substrings from the input text. Do not correct spelling or alter capitalization.
2. DO NOT extract generic words (like 'workshop', 'bibliotheek', 'kantine', 'eten', 'voeten', 'blij').
3. DO NOT extract standalone numbers or grades (like '1', '4', '8.5').
4. The output must be parsable by Python's json.loads().
```

**User message voor de LLM:** de (reeds deels geanonimiseerde) tekst na Presidio + EU-PII-safeguard (`eu_pii_anonymized`).

**Tag mapping na extractie:** `names`→`[NAME]`, `titles`→`[TITLE]`, `locations`→`[LOCATION]`, `courses`→`[COURSE/DEPT]`, `pii`→`[PII]`, `physical`→`[PHYSICAL_DESCRIPTOR]` (langste matches eerst).

---

## Stap 10: Parallelisme — batch vs `OLLAMA_NUM_PARALLEL`

**Datum:** 2026-04-04

**Wat is er gedaan:**
- In compose: `OLLAMA_NUM_PARALLEL=${OLLAMA_NUM_PARALLEL:-15}` (via `.env` te overschrijven). In de app stuurt `batch_size` (default 15 in `process_dataframe_async`) zoveel gelijktijdige `anonymize_text_async`-taken tegelijk naar Ollama — **server-side** bepaalt `OLLAMA_NUM_PARALLEL` hoeveel daarvan echt parallel door het model gaan.

**Waarom:**
Als **parallel < batch**, stapelen requests in de wachtrij → lagere throughput. Hogere parallel op kleine GPU: risico op OOM/timeouts, maar vaak betere wall time (zie Stap 12).

**Bronnen:**
- Ollama env in logs (`OLLAMA_NUM_PARALLEL`), eigen GPU-limiet.

**Zelf bedacht:**
Compose-default en app-`batch_size` expliciet op elkaar afstemmen na meten (zie Stap 12).

---

## Stap 11: Benchmark / vergelijking (referentie)

**Datum:** 2026-04-04

**Wat is er gedaan:**
- Resultaten en aanbevelingen vastgelegd in `compare_vllm(small)_ollama(big)/readme.md` (o.a. Qwen 3B AWQ + vLLM vs grotere Ollama-modellen op dezelfde CSV).

**Waarom:**
Portfolio-evidence voor modelkeuze op beperkte hardware.

**Bronnen:**
- Eigen runs op `safe_cleaned_survey_long_format_q(all).csv`.

**Zelf bedacht:**
Welk model wanneer gebruiken (snelheid vs kwaliteit).

---

## Stap 12: Metingen — `batch_size` × `OLLAMA_NUM_PARALLEL` (Ollama)

**Datum:** 2026-04-04

**Wat is er gedaan:**
- Inzicht: met **batch=2** in de app maar **`OLLAMA_NUM_PARALLEL=1`** in Compose kon Ollama nog steeds maar **één** verzoek tegelijk door het model jagen; extra requests **staan in de wachtrij**. Doorzetten van de batch-size alleen helpt dan niet voor throughput — parallel moet mee omhoog.
- **Kleine dataset** (snelle sanity-run): `OLLAMA_NUM_PARALLEL` gevarieerd (o.a. 5, 10, 15). Rond **10** het snelst (**~15–16 s** eindtijd); bij **15** iets trager (**~19 s**) — meer gelijktijdige werkunits, maar ook meer afruil (scheduling, KV-cache, eventuele contention).
- **Grote dataset** (676 regels, `safe_cleaned_survey_long_format_q(all).csv`): eerdere run met **batch=2** (en effectief lage parallel) **~30 minuten** wall time.
- **Zelfde CSV met batch=15 en `OLLAMA_NUM_PARALLEL=15`:** start **~15:56**, klaar **~16:11** → **~15 minuten** wall time (logs: `Async anonymization process completed.` o.a. **16:11:27**). Ruwweg **2× sneller** dan de ~30 min-baseline. Ollama-log: laatste `POST /api/chat` in die run **~10,1 s**; agent parseerde JSON uit een **markdown code fence** (`Parsed LLM JSON from markdown code fence`).
- **GPU-gedrag (Task Manager, GPU 3D):** bij **lage** parallel stond gebruik **~40%** gemiddeld, relatief **vlak**. Bij **parallel=15** veel **scherpere pieken** (kort hoog, daarna weer laag) — dat hoort bij burst-achtige verwerking: de GPU wordt kort maximaal belast per wave, niet constant “smooth”.

**Waarom dit verschil zichtbaar is:**
- Meer parallel = meer overlappende forward passes → hogere piekbelasting en zichtbaardere burst-pattern op de util-grafiek.
- Gemiddeld percentage zegt niet alles: **korte pieken** kunnen alsnog goed zijn voor **totale doorlooptijd**, zolang er geen throttling/OOM is.

**Bronnen:**
- Eigen metingen (kleine dataset timings; grote dataset ~30 min @ batch 2 vs **~15 min** @ batch 15 + parallel 15).
- Docker logs `privacy-agent` / `ollama` (tijdstempels completion).
- Windows Taakbeheer GPU (3D), screenshot t.b.v. portfolio (spiky pattern bij hoge parallel).

**Zelf bedacht:**
- **Sweet spot** voor kleine run: **~10** parallel (sneller dan 5, iets sneller dan 15 in die test).
- Grote run bevestigt: **parallel en batch alignen** levert grote winst op wall time; bij problemen (OOM/timeout) parallel/batch terug naar 8–10 en opnieuw meten.

---

## Stap 13: Vergelijking output — batch 2 vs batch 15 (zelfde model, Gemini-analyse)

**Datum:** 2026-04-04

**Context:** Twee export-CSV’s na anonimisatie: één run met **batch size 2**, één met **batch size 15** (zelfde Ollama-model, zelfde pipeline). De ruwe outputs zijn niet byte-voor-byte gelijk; een externe LLM (Gemini) is gebruikt om het **verschil in karakter** te beschrijven — niet als formele meting, wel als **oriënterende tekstanalyse** voor portfolio en besluitvorming.

**Gebruikte prompts (letterlijk):**

1. *« de 2 csv bestnden met batch size 2 en batch size 15 »*  
   *« komen deze 2 overheen met elkaar? allebei zelfde modellen, alleen de ene had een grotere batch »*

2. *« er is ollama gebruikt hiervoor. wat zijn de verschillen en wat is betere pii en wat is bruikbaarder »*

**Gesprek (deelbaar):** [Gemini — batch 2 vs 15 analyse](https://gemini.google.com/share/84d4aa954d0f)

**Verificatie — klopt de context t.o.v. logs en compose?**

| Check | Uitkomst |
|--------|----------|
| **`OLLAMA_NUM_PARALLEL` in Ollama-logregels** | Staat **niet** in `[GIN]`-regels; alleen bewijs via omgeving of compose. |
| **Actieve waarde in container** | `docker compose exec ollama env` → **`OLLAMA_NUM_PARALLEL=15`** (gecontroleerd op ontwikkelmachine). |
| **Waar komt 15 vandaan?** | `docker-compose.yml`: `${OLLAMA_NUM_PARALLEL:-15}`. Lokale `.env` **zet deze variabele niet** → default **15**. |
| **Batch size (app)** | Staat in **privacy-agent**-log: `Starting async anonymization ... batch size: N`. Die regel altijd bewaren bij een run; in een lang `docker compose up`-terminal kan die wegscrollen — voor portfolio: log export of `docker compose logs privacy-agent \| findstr "Starting async"`. |
| **Overlappende requests (indirect bewijs parallel > 1)** | In ollama-log: meerdere `POST "/api/chat"` met status 200 in **dezelfde seconde** (bijv. `16:08:16`, `16:11:24–26`) — past bij meerdere gelijktijdige chats, dus **niet** `NUM_PARALLEL=1`. |
| **Aantal rijen vs Gemini (“675”)** | Bron-CSV `safe_cleaned_survey_long_format_q(all).csv`: **676 regels** totaal; met **1 header** → **675 datarijen** — komt overeen met Gemini’s “675 rijen”. |

**Conclusie:** Voor de **batch-15**-run is **`OLLAMA_NUM_PARALLEL=15`** hard te maken via `docker compose exec`. Voor de **batch-2**-run moet je dezelfde check **op dat moment** in de logs of via `env` hebben gehad; als destijds `OLLAMA_NUM_PARALLEL=1` stond terwijl de app al `batch_size=2` stuurde, was de bottleneck **server-side serial** (zie Stap 12) — dat verklaart traagheid, los van het CSV-diff-verhaal.

**Wat Gemini antwoordde (kern — 1e vraag):**
- **Nee, geen 100% match.** Op **~675 rijen** ca. **37 verschillen** (~5,5%) — grotendeels gelijk, maar batch-grootte hangt samen met **net andere** modelkeuzes in grijze zones.
- **Voorbeelden** die Gemini uit de data haalde:
  - **Gebouwen:** oorspronkelijk o.a. "building A" … "building D"; batch-2 laat meer staan; batch-15 zet vaker **[LOCATION]**-labels.
  - **Software:** "Tableau / PowerBI" — batch-2 o.a. Tableau als **[NAME]**; batch-15 ook PowerBI als **[COURSE/DEPT]** (verschillende interpretatie van dezelfde regel).
  - **Tagsyntax:** batch-2 soms **dubbele haken** (`[[NAME]]`); batch-15 vaker netjes **`[NAME]`** (Gemini merkt dit op als voordeel voor batch-15).
  - **Fysiek / randcase:** zin met "thick accent" — batch-15 markeerde dat als **[PHYSICAL_DESCRIPTOR]**, batch-2 niet (volgens Gemini: batch-15 soms **agressiever** in grijze gevallen).

**Technische verklaring door Gemini (parafrase):**  
Gemini schreef o.a. over **tensor-batching**, **padding tokens**, **Flash Attention** en **floating-point** — als verklaring waarom grotere batches kleine verschuivingen in twijfelgevallen kunnen geven. **Nuance voor dit project:** onze app stuurt **parallelle chat-requests** naar Ollama (`batch_size` + `OLLAMA_NUM_PARALLEL`), niet per se dezelfde setup als **vLLM continuous batching** in één gebatche forward pass. De **37 verschillen** zijn dus plausibel (volgorde, concurrentie, JSON/prompt-randgevallen), maar de **GPU-padding-story** moet je in portfolio als **hypothese van Gemini** zien — **eigen bron**: Ollama-docs / reproduceerbare diff, niet alleen dit antwoord.

**Wat Gemini antwoordde (kern — 2e vraag, Ollama):**
- **Verschil in gedrag:** batch-15 **gevoeliger/agressiever** in twijfelgevallen; batch-2 **conservatiever** (meer context intact voor analyse door docenten).
- **“Betere” PII:** afhankelijk van doel — **maximaal maskeren** → neiging naar strengere run (batch-15); **leesbare feedback** → neiging naar conservatiever (batch-2). Voor “harde” PII zou Gemini verwachten dat beide **vergelijkbaar** zijn; verschillen vooral in **grijze zones**.
- **Bruikbaarheid:** Gemini adviseerde **batch-15 (of 10–15)** als **praktischer** vanwege **snelheid**, met acceptabele afwijking in randgevallen; expliciet **Gemma-4** + batch **10–15** genoemd als balans (dit sluit aan bij eigen metingen: ~15 min vs ~30 min op grote set).

**Bronnen:**
- Twee CSV-exportbestanden (batch 2 vs batch 15), zelfde model.
- [Gesprek Gemini](https://gemini.google.com/share/84d4aa954d0f); prompts hierboven (AI-transparantie).
- `docker compose exec ollama env` (parallel-check); compose + `.env`.

**Zelf bedacht:**
- Gemini = **hulpmiddel om verschillen te categoriseren**, geen vervanging van statistische validatie; **37 verschillen** desnoods handmatig spot-checken op false positives/negatives.
- Voor decision log: vastleggen **waarom** je batch 15 accepteert (snelheid + acceptabel diff-profiel) óf waar je batch verlaagt voor **stabiliteit** in productie.

---

---

## Stap 14: Succescriteria opstellen voor Input Security (recall & datakwaliteit)

**Datum:** 2026-04-15

**Wat is er gedaan:**
- Kritisch doorgedacht of laag 3 (LLM) weggehaald kan worden; conclusie: laag 3 is het enige dat **fysieke beschrijvingen** (`kaal`, `rode jas`) detecteert — indirecte identificatoren die laag 1+2 structureel missen.
- Vijf concrete, meetbare succescriteria geformuleerd:
  - **SC-1** PII-detectierate per laag (recall op geannoteerde testset)
  - **SC-2** False-positiverate per laag (precision op schone tekst)
  - **SC-3** Unieke vangst laag 3 — fysieke descriptoren apart meten
  - **SC-4** Datakwaliteitsscore na anonimisering (menselijke beoordeling 1–5)
  - **SC-5** `[NEEDS_REVIEW]`-percentage ≤ 2%

**Waarom:**
De discussie "laag 3 weghalen" was puur intuïtie; zonder meting is die beslissing niet verdedigbaar. SC-1 t/m SC-3 geven een empirische onderbouwing.

**Bronnen:**
- Analyse van `privacy_agent.py` (wat doet elke laag uniek); GDPR over indirecte identificatoren.

**Zelf bedacht:**
De splitsing in SC-3 (fysieke descriptoren apart) — dit type PII is AVG-relevant maar niet meetbaar zonder expliciete test cases; vandaar aparte criterium.

---

## Stap 15: Testdataset aanmaken (100 rijen, gelabelde PII)

**Datum:** 2026-04-15

**Wat is er gedaan:**
- `test_dataset_v2.csv` en `test_dataset_v2.xlsx` aangemaakt via `build_test_dataset.py`.
- 100 rijen, 10 per thema (Slow grading by Smith, Insufficient contact hours, Course depth & quality, Unclear assessment criteria, Poor teacher communication, Teaching style & explanation quality, Workload & time management, Student support & teacher availability, Technology & online resources, Diversity & inclusivity).
- 3 kolommen:
  - `thema’s` — het onderwerp
  - `voorkomende tekst van pii of indirect wat eruit gehaald moet worden` — gelabelde letterlijke waarden (`naam:Smith, email:j.smith@fontys.nl`)
  - `open antwoord` — de feedbackzin (80% NL / 20% EN)
- PII-verdeling: 73x naam, 15x gebouw (R1, R10, TQ 3.14, lokaal 2.05, etages), 15x indirect_fysiek, 13x studentnummer, 8x email, 3x username, 2x telefoon, 1x obfuscated_email.
- Validatie ingebouwd: elk `te_detecteren`-waarde staat letterlijk in de bijbehorende feedbackzin.

**Waarom:**
SC-1 t/m SC-3 zijn niet meetbaar zonder een geannoteerde testset met bekende ground truth.

**Bronnen:**
- Eigen ontwerp; Python `csv` + `openpyxl`.

**Zelf bedacht:**
Pipe-separator (`|`) vervangen door `type:waarde`-formaat per kolom zodat programmatische recall-check mogelijk is met een eenvoudige split op `,` en `:`.

---

## Stap 16: Recall check script (`check_anonymization.py`)

**Datum:** 2026-04-15

**Wat is er gedaan:**
- `check_anonymization.py` geschreven: laadt de geanonimiseerde output-CSV, vergelijkt per rij de `te_detecteren`-waarden met de `anonymized_open antwoord`-kolom (case-insensitief).
- Voegt twee kolommen toe: `geanonimiseerd` (True/False) en `gemiste_pii` (welke waarden nog staan).
- Exporteert groen/rood Excel met per-thema kleurcodering + een Summary-tabblad.
- Print recall, per-thema breakdown en top-10 gemiste PII-waarden naar terminal.

**Resultaat eerste meting (lagen 1+2+3, Qwen2.5-3B-AWQ):**
- Recall: **77/100 = 77%**
- 10/10: Technology & online resources
- Zwakst: Course depth & quality (5/10)
- Meest gemist: `2e etage`, `De Vries`, `de baard`, `kale docent` → allemaal indirect/gebouw (laag 3-categorie)

**Waarom:**
Meting voor SC-1 en SC-3; de resultaten laten zien dat laag 3 indirecte PII gedeeltelijk mist, maar wel degelijk toevoegt ten opzichte van lagen 1+2.

**Bronnen:**
- Eigen code; `safe_test_dataset_v2 (1).csv` (output na pipeline).

**Zelf bedacht:**
Excel-export met groen/rood per rij en Summary-tab — makkelijker voor portfolio-bewijslast dan alleen terminal output.

---

## Stap 17: Bug fix — CSV parsing crash (ParserError + encoding)

**Datum:** 2026-04-15

**Wat is er gedaan:**
- Fout: uploaden van een semicolon-delimited CSV (testdataset) gaf `500 Internal Server Error` in de UI.
- Oorzaak: `pd.read_csv` defaultt naar komma als separator; na `UnicodeDecodeError`-fallback naar `latin-1` volgde `pandas.errors.ParserError: Expected 1 fields in line 5, saw 2`. Dit is een onbehandelde exception → Starlette retourneert plain-text 500, niet JSON.
- Fix in `app.py`: `_read_csv_robust()` probeert 4 encodings × 3 separators (`,`, `;`, `\t`) totdat een parse met meer dan 1 kolom slaagt. Geeft een `HTTPException(400)` met leesbare melding als alles faalt.
- Fix in `index.html`: `response.json()` vervangen door content-type check — bij non-JSON response toont de UI de werkelijke serverfout in plaats van een cryptische `Unexpected token ‘I’...`-melding.

**Waarom:**
De fout was ondiagnosticeerbaar voor de gebruiker; het JS-probleem maskeerde de echte oorzaak (CSV-dialect).

**Bronnen:**
- Docker logs `privacy-agent-1` (stacktrace zichtbaar gemaakt door gebruiker).

**Zelf bedacht:**
`_read_csv_robust()` als aparte helper — herbruikbaar voor alle toekomstige CSV-endpoints.

---

## Stap 18: Recall check ingebouwd in de API en UI

**Datum:** 2026-04-15

**Wat is er gedaan:**
- Twee nieuwe form-parameters toegevoegd aan `/api/anonymize`:
  - `run_check: bool` (default `False`) — schakelaar
  - `pii_reference_column: str` — naam van de PII-labelkolom (configureerbaar)
- `_run_recall_check()` in `app.py`: zelfde logica als het losse script, geeft recall, per-thema breakdown en top gemiste waarden terug als JSON in de response.
- UI: nieuw blok "5. Recall Check" met checkbox; als ingeschakeld verschijnt een tekstveld voor de kolomnaam (ingevuld met de standaard testdataset-naam).
- Na anonimisering toont de UI direct: recall % (groen ≥90%, oranje ≥70%, rood <70%), inklapbare per-thema tabel, inklapbare lijst gemiste PII-waarden.
- Als de referentiekolom niet bestaat in het geüploade CSV → duidelijke waarschuwing, geen crash.

**Waarom:**
Het losse script vereiste handmatig bestandsbeheer; ingebouwd in de UI maakt meten na elke run direct mogelijk zonder extra stap.

**Bronnen:**
- `check_anonymization.py` (stap 16) als basis; FastAPI Form-parameters docs.

**Zelf bedacht:**
Schakelaar standaard **uit** zodat de check productie-runs niet vertraagt; configureerbare kolomnaam zodat het werkt met elke testdataset-structuur.

---

## Stap 19: False positive detectie toegevoegd aan recall check

**Datum:** 2026-04-15

**Wat is er gedaan:**
- Nieuwe functie `find_extra_replacements()` in `check_anonymization.py` en `_find_extra_replacements()` in `app.py`.
- Gebruikt `difflib.SequenceMatcher` op woordniveau om vervangen segmenten te vinden. Per segment: elk woord individueel gecontroleerd — als het woord niet in de verwachte PII-lijst staat en langer is dan 2 tekens, wordt het als onverwacht gemarkeerd.
- Nieuwe kolom `extra_geanonimiseerd` in de output: komma-gescheiden lijst van woorden die onverwacht zijn anonimiseerd.
- Excel-kleuren uitgebreid: groen = volledig geanonimiseerd zonder extras, **oranje** = volledig geanonimiseerd maar extra tekst verwijderd, rood = PII nog aanwezig.
- Terminaloutput toont "Meest onverwacht verwijderde woorden (false positives)" met tellingen.
- UI toont naast de recall ook een badge (oranje/groen) voor false positives en een inklapbare sectie "Onverwachte vervangingen".

**Waarom:**
De recall-meting was eenzijdig: het zei alleen wat er gemist werd, niet wat er te veel was. Een voorbeeld uit de data: `docent` werd vervangen door `[TITLE]` terwijl alleen `Jansen` verwacht was. Dit is relevant voor het beoordelen van SC-4 (precisie).

**Bronnen:**
- Python `difflib` docs; eigen ontwerp op basis van geobserveerd gedrag.

**Zelf bedacht:**
Segmentcontrole op woordniveau i.p.v. op segment-niveau — anders maskeert één verwacht woord in een segment alle overige onverwachte woorden in datzelfde segment.

---

## Stap 20: Bug fix — false positive detectie toonde verkeerde data

**Datum:** 2026-04-15

**Wat is er gedaan:**
- Bug 1 (`orig_col` in `_run_recall_check`): de originele tekstkolom werd bepaald als "eerste kolom die niet de anonimiseer- of PII-kolom is" → dit pakte `thema’s` in plaats van `open antwoord`. De diff liep dus tegen de thema-naam, wat nep-matches gaf. Opgelost door `orig_col` af te leiden van `anon_col` via `anon_col[len("anonymized_"):]`.
- Bug 2 (segmentcheck): het hele vervangen segment werd als één string gecontroleerd. Als segment `"docent Jansen"` was en `"Jansen"` verwacht, vond de check `"Jansen" in "docent Jansen"` → True en markeerde het hele segment als verwacht, waardoor `"docent"` niet meer zichtbaar was. Opgelost door woord-voor-woord te controleren binnen het segment.
- Weergave vereenvoudigd: output van `’docent’ → [TITLE]` teruggebracht naar alleen `docent`.

**Waarom:**
Bij bijna alle rijen stond onterecht extra_geanonimiseerd-data terwijl de pipeline correct werkte. Twee aparte bugs die samen het resultaat onbruikbaar maakten.

**Bronnen:**
- Eigen foutanalyse op basis van geobserveerde output.

**Zelf bedacht:**
Afleiden van `orig_col` uit `anon_col` via prefix-stripping is robuuster dan kolom-positie gebruiken, omdat de kolomvolgorde per dataset kan verschillen.

---

## Stap 21: Sync-duplicaten verwijderd uit `privacy_agent.py`

**Datum:** 2026-04-15

**Wat is er gedaan:**
- `anonymize_text()` (sync, ~125 regels) verwijderd — identieke logica als `anonymize_text_async()`, alleen de LLM-aanroep verschilde.
- `process_dataframe()` (sync, ~40 regels) verwijderd — identieke loop als `process_dataframe_async()`.
- `main.py` bijgewerkt: importeert nu `process_dataframe_async` en roept het aan via `asyncio.run(...)`.
- Ongebruikte imports `tqdm` en `time` verwijderd.
- Resultaat: 653 → 483 regels (-170 regels).

**Waarom:**
Twee near-identieke functies verhoogden de onderhoudslast: een wijziging in de pipeline (bijv. een nieuwe PII-categorie) moest op twee plekken worden doorgevoerd. De sync-versies werden alleen gebruikt door de CLI (`main.py`), die prima via `asyncio.run()` de async-versie kan aanroepen.

**Bronnen:**
- Eigen analyse; Python `asyncio.run()` docs.

**Zelf bedacht:**
Sync-versie niet omgebouwd maar volledig verwijderd — `asyncio.run()` in `main.py` is de minste wijziging met het grootste effect op de codebase.

---

## Stap 22: Recall analyse laag 1+2 → FLOOR_REFERENCE regex toegevoegd

**Datum:** 2026-04-20

**Prompt (letterlijk):**
> look at this:
> 📊 Recall: 80% (80/100 rijen volledig geanonimiseerd)
> ⚠️ 20 rij(en) met onverwachte vervangingen
> Per thema
> Meest gemiste PII-waarden (false negatives): rolstoelgebruiker (2x), De Vries (2x), kale docent (1x), derde etage (1x), lange man met bril (1x), 3e etage (1x), 2e etage (1x), 876543 (1x), korte blonde haren (1x), 345678 (1x)
> Onverwachte vervangingen (false positives): Mevrouw (7x), mevrouw (6x), Meneer (4x), Software (1x), Engineering (1x), heer (1x), Nederlandstalige (1x)
>
> this is only with layer 1+2. what can i change in layer 1 based on this data to catch something?
> it is built with presidio so look at it, dont change anyting, dont hardcode, only add regex to catch thing

**Wat is er gedaan:**
- Recall-uitkomst geanalyseerd per categorie: wat kan regex vangen vs. wat is puur semantisch.
- Conclusie: `3e etage`, `2e etage`, `derde etage` zijn vangbaar met een patroon; fysieke beschrijvingen (`rolstoelgebruiker`, `kale docent`, `korte blonde haren`) en namen (`De Vries`) zijn niet zonder grote false positive risico’s met regex te vangen.
- Nieuw `FLOOR_REFERENCE`-recognizer toegevoegd aan `PRESIDIO_PATTERN_DEFINITIONS` in `privacy_agent.py`:
  - `\b\d+[e]\s+etage\b` — vangt `3e etage`, `2e etage` (score 0.9)
  - `\b(?:eerste|tweede|derde|...)\s+etage\b` — vangt `derde etage` etc. (score 0.9)
- `FLOOR_REFERENCE` toegevoegd aan `PRESIDIO_OPERATORS` (`→ [LOCATION]`) en als eigen config-toggle in `build_presidio_operators`.

**Vervolgprompt:**
> also add it as an option to select it in the frontend, so i can disable it if needed

- Checkbox "Floor References (e.g. 3e etage) [LOCATION]" toegevoegd aan sectie 4 in `index.html` (standaard aangevinkt).
- `formData.append(‘anon_floors’, ...)` toegevoegd in JS.
- `anon_floors: bool = Form(True)` + `"floors": parse_bool(anon_floors)` toegevoegd in `app.py`.

**Waarom:**
Etage-aanduidingen zijn indirecte locatie-identificatoren (AVG-relevant); het patroon `Xe etage` is zo specifiek dat false positives nauwelijks voorkomen. Fysieke beschrijvingen zijn semantisch — die blijven voor laag 3.

**Bronnen:**
- Eigen recall-meetresultaten (testdataset v2, laag 1+2).
- Presidio `PatternRecognizer` docs.

**Zelf bedacht:**
Keuze om alleen de etage-patronen met regex te doen en de rest (fysieke descriptoren, namen) bewust bij laag 3 te laten — op basis van false positive risico-analyse.

---

## Stap 23: AVG/Fontys beleidswiki analyse → NL_BSN en Dutch postcode toegevoegd

**Datum:** 2026-04-20

**Prompt (letterlijk):**
> https://beleidswiki.fhict.nl/doku.php?id=beleid:regel-_en_wetgeving_privacy
> https://autoriteitpersoonsgegevens.nl/themas/basis-avg/privacy-en-persoonsgegevens/wat-zijn-persoonsgegevens
>
> what can presidio catch from this

- Beide bronnen opgehaald en vergeleken met de bestaande Presidio-configuratie.
- Resultaat: een gap-analyse per PII-categorie (wat al gevangen wordt, wat detecteerbaar is maar niet gekoppeld, wat structureel ontbreekt).

**Vervolgprompt:**
> yes

- Twee nieuwe recognizers toegevoegd aan `PRESIDIO_PATTERN_DEFINITIONS`:
  - **`NL_BSN`**: `\b\d{3}\.\d{2}\.\d{3}\b` (score 0.95, geformatteerd) + `\b\d{9}\b` (score 0.75, met context `bsn`, `burgerservicenummer`, `sofinummer`).
  - **`DUTCH_POSTCODE`**: `\b\d{4}\s?[A-Z]{2}\b` (score 0.9, context `postcode`, `adres`, `straat`).
- Beide toegevoegd aan `PRESIDIO_OPERATORS` en als eigen config-toggle in `build_presidio_operators`.
- Frontend (`index.html`): checkboxes "BSN (burgerservicenummer) [PII]" en "Dutch Postcodes (e.g. 3061 AW) [LOCATION]" toegevoegd, beide standaard aangevinkt.
- `app.py`: `anon_bsn` en `anon_postcode` als form-parameters + config-keys.

**NL_BSN is niet auto-registered door Presidio 2.2.353** — handmatige registratie via `PRESIDIO_PATTERN_DEFINITIONS` is vereist (bevestigd na analyse).

**Waarom:**
BSN is juridisch de meest gevoelige Nederlandse identifier; postcodes zijn indirecte identificatoren onder de AVG. Beide staan expliciet in de AP-definitie van persoonsgegevens maar ontbraken volledig in laag 1.

**Bronnen:**
- [Fontys beleidswiki — Privacy](https://beleidswiki.fhict.nl/doku.php?id=beleid:regel-_en_wetgeving_privacy)
- [Autoriteit Persoonsgegevens — Wat zijn persoonsgegevens?](https://autoriteitpersoonsgegevens.nl/themas/basis-avg/privacy-en-persoonsgegevens/wat-zijn-persoonsgegevens)
- Presidio `PatternRecognizer` docs; eigen analyse van `requirements.txt` (versie 2.2.353).

**Zelf bedacht:**
Elk pattern als aparte toggle in de UI — consistent met de aanpak van `anon_student_nr` en `anon_floors`, zodat je per categorie kunt testen wat false positives veroorzaakt.

---

## Stap 24: Alle false positives/negatives tonen in UI (geen top-10 limiet)

**Datum:** 2026-04-20

**Prompt (letterlijk):**
> is it posible that it show all the Onverwachte vervangingen (false positives) and Meest gemiste PII-waarden (false negatives)

**Wat is er gedaan:**
- In `app.py`: `Counter(...).most_common(10)` vervangen door `Counter(...).most_common()` (geen limiet) voor zowel `top_missed` als `top_extras`.
- Frontend hoefde niet aan te worden aangepast — die itereert al over de volledige lijst.

**Waarom:**
De top-10 limiet verborg systematische patronen; bij een testset van 100 rijen met 20+ false positive-typen was de volledige lijst nodig om te beoordelen welke categorieën de meeste vervuiling veroorzaken.

**Bronnen:**
- Python `collections.Counter` docs.

**Zelf bedacht:**
Geen apart paginering gebouwd — bij een testset van 100 rijen is de volledige lijst altijd overzichtelijk genoeg.

---

## Stap 25: Layer 1 verbeteringen — DUTCH_PHONE en DUTCH_HONORIFIC

**Datum:** 2026-04-20

**Prompts (letterlijk):**
> if i only select layer 1 i get this: [recall 64%, false negatives incl. 06-12345678, Mevrouw als false positive]
> if i only select layer 2 i get this: [recall 63%]
> doe 1 en voor meneer mevrouw heer wil ik dat dit vervangen word door docent placeholder

**Wat is er gedaan:**

**1. DUTCH_PHONE recognizer toegevoegd** (`PRESIDIO_PATTERN_DEFINITIONS`):
- `\b06[-\s]\d{2}[-\s]?\d{2}[-\s]?\d{2}[-\s]?\d{2}\b` (score 0.9) — vangt `06-12345678`, `06 12 34 56 78`
- `\b\+316\d{8}\b` (score 0.95) — vangt `+31612345678`
- Presidio’s ingebouwde `PHONE_NUMBER` miste het Nederlandse `06-XXXXXXXX` dash-formaat; expliciete regex lost dit op.
- Volgt de `pii`-toggle in UI/API.

**2. DUTCH_HONORIFIC recognizer toegevoegd** (`PRESIDIO_PATTERN_DEFINITIONS`):
- Regex: `\b(?:Mevrouw|mevrouw|Meneer|meneer|Mevr\.|mevr\.|Dhr\.|dhr\.|heer|Heer)\b` (score 0.9)
- Vervangt naar `[TITLE]` in plaats van `[NAME]` (spaCy NER classificeerde deze als PERSON).
- Volgt de `titles`-toggle — al aanwezig in de UI als "Roles & Titles [TITLE]".

**Resultaat (Layer 1 only, voor vs. na):**
- Recall: **64% → 69%** (+5 rijen correct anoniem)
- Telefoonnummers (`06-12345678`, `06-23456789`) verdwenen uit false negatives ✅
- Honorifics nu `[TITLE]` i.p.v. `[NAME]` ✅
- False positive teller steeg (18 → 23 rijen): regex vangt meer Mevrouw/Meneer-instanties dan spaCy NER deed — dit is gewenst gedrag; de testdataset labelt honorifics niet als PII, waardoor ze als "extra" worden geteld.

**Waarom:**
Presidio’s built-in phone recognizer is te conservatief voor NL-formaten; de honorific-fix corrigeert een structurele NER-misclassificatie die tot verkeerde tags leidde.

**Bronnen:**
- Eigen recall-meetresultaten (testdataset v2, layer 1 only).
- Presidio `PatternRecognizer` docs.

**Zelf bedacht:**
`DUTCH_HONORIFIC` koppelen aan de bestaande `titles`-toggle (niet een nieuwe checkbox) — de toggle bestond al in de UI voor laag 3, nu ook geldig voor laag 1.

---

## Stap 26: Evidence document layer 1 progressie aangemaakt

**Datum:** 2026-04-20

**Prompt (letterlijk):**
> voeg de stappen toe en maak een evindence of the improvement with the results

**Wat is er gedaan:**
- Stappen 22–26 toegevoegd aan `stappen.md`.
- `LAYER1_IMPROVEMENT_EVIDENCE.md` aangemaakt met kwantitatieve vergelijking van Layer 1 recall over alle iteraties, per-thema breakdown, en analyse van resterende gaps.

**Waarom:**
Portfolio-evidence voor SC-1 (PII-detectierate per laag) en SC-2 (false-positiverate). De iteratieve verbetering van Layer 1 is nu aantoonbaar met meetbare data.

---

## Stap 27: CSV vs Parquet — inputformaat en bottleneck analyse

**Datum:** 2026-04-21

**Prompt (letterlijk):**
> is it better to use a parquet file then a csv if i look to the speed of the process, in the end situation it has around 15000 rows to anonymize

**Wat is er gedaan:**
- Geanalyseerd waar de werkelijke verwerkingstijd zit bij 15.000 rijen.
- Conclusie: `pd.read_csv()` duurt ~0,1–0,3 seconden voor 15k rijen; Parquet scheelt op die stap maximaal 80ms — verwaarloosbaar.
- De echte bottleneck per rij: Layer 1 (Presidio/spaCy, ~10–50ms), Layer 2 (transformer, ~50–200ms), Layer 3 (LLM, ~500ms–3s).
- Geen codewijziging gemaakt; advies: focus op Layer 2 batching en `batch_size` verhogen, niet op het inputformaat.

**Waarom:**
Parquet is gunstig als je dezelfde data tientallen keren leest of grote binaire kolommen hebt. Voor één lees- en schrijfoperatie van tekstrijen is het verschil met CSV niet meetbaar ten opzichte van de verwerkingstijd per rij.

**Bronnen:**
- Eigen analyse van `privacy_agent.py` (tijdverdeling per laag); pandas docs.

**Zelf bedacht:**
Beslissing om het inputformaat *niet* te wijzigen als performancemaatregel — de bottleneck zit in de ML-inferentie, niet in I/O.

---

## Stap 28: Opsplitsen `privacy_agent.py` in laagbestanden

**Datum:** 2026-04-21

**Prompt (letterlijk):**
> now it is all in 1 file but is it not more easier if i had 3 separate files so there is structure of the layers as files?

**Wat is er gedaan:**
- `src/core/privacy_agent.py` (567 regels) opgesplitst in vier bestanden:
  - `src/core/layers/layer1_presidio.py` — Presidio-setup, pattern definitions, operators, `anonymize_with_presidio()`
  - `src/core/layers/layer2_eu_pii.py` — HF-pipeline initialisatie, `eu_pii_safeguard_anonymize()`, nieuw: `eu_pii_safeguard_anonymize_batch()`
  - `src/core/layers/layer3_llm.py` — LLM-clients (vLLM/Ollama), `get_dynamic_prompt()`, `parse_llm_json_response()`, `anonymize_with_llm_async()`
  - `src/core/privacy_agent.py` — alleen orchestratie: importeert lagen, ketent ze, beheert batching en progress
- `src/core/layers/__init__.py` aangemaakt (leeg pakket).
- `app.py` en `main.py` ongewijzigd — beiden importeren alleen `process_dataframe_async`, waarvan de signatuur gelijk bleef.

**Layer 2 batching toegevoegd:**
- `_apply_eu_pii_entities()` als gedeelde helper geëxtraheerd uit `eu_pii_safeguard_anonymize()`.
- `eu_pii_safeguard_anonymize_batch(texts, config)` roept `eu_pii_ner(texts)` eenmalig aan per batch in plaats van per rij — de HF-pipeline geeft een `list[list[dict]]` terug.
- `process_dataframe_async()` herschreven: Layer 1 per tekst (sync), Layer 2 als één batch-aanroep, Layer 3 async/concurrent per tekst.

**Waarom:**
Één bestand van 567 regels met drie onafhankelijke verantwoordelijkheden maakt onderhoud moeilijker. Elke laag heeft nu één bestand dat zelfstandig te lezen en te testen is. De batch-aanpak voor Layer 2 verlaagt ook het aantal transformer-aanroepen van N naar N/batch_size.

**Bronnen:**
- HF `transformers.pipeline` docs (batch_size parameter).

**Zelf bedacht:**
`_apply_eu_pii_entities()` als private helper om dubbele vervangingslogica te vermijden tussen de single- en batch-variant.

---

## Stap 29: Parquet en JSONL als uitvoerformaten

**Datum:** 2026-04-21

**Prompt (letterlijk):**
> make a convert file and add after the anonymization i want that there is a option to convert it to parquet or jsonl, make a service

**Wat is er gedaan:**
- `src/core/data_converter.py` aangemaakt met:
  - `to_parquet(df, path)` — schrijft via `pyarrow`
  - `to_jsonl(df, path)` — schrijft JSON Lines (`orient=’records’, lines=True, force_ascii=False`)
  - `convert_csv(csv_path, fmt)` — leest bestaande output-CSV en converteert naar gevraagd formaat
- Nieuw API-endpoint `GET /api/convert/{filename}?format=parquet|jsonl` toegevoegd aan `app.py`.
- `pyarrow>=14.0.0` toegevoegd aan `requirements.txt`.
- `index.html`: drie downloadknoppen na anonimisering — CSV (groen), Parquet (paars), JSONL (oranje). Bestandsnaam dynamisch afgeleid van de `download_url` in de API-response.

**Waarom:**
Parquet is efficiënter voor downstream data-analyse; JSONL is handig voor regelsgewijze verwerking of import in andere tools. De conversie gebeurt on demand (niet bij elke run) zodat de verwerkingstijd niet toeneemt.

**Bronnen:**
- pandas `to_parquet` / `to_json` docs; FastAPI `FileResponse`.

**Zelf bedacht:**
Conversie on-the-fly via een apart endpoint — de output-CSV blijft altijd de primaire opslag; formaten worden pas aangemaakt als de gebruiker erop klikt.

---

## Stap 30: Parquet als invoerformaat

**Datum:** 2026-04-21

**Prompt (letterlijk):**
> make it possible that i add a parquet file as input so i can test the anonymizer with parquet data to test if it is faster. still csv must be available to input

**Wat is er gedaan:**
- `src/core/data_loader.py` herschreven:
  - `load_csv()` — robuuste multi-encoding/separator logica (overgezet vanuit `app.py`)
  - `load_parquet()` — laadt via pyarrow
  - `load_data()` — dispatcht op bestandsextensie (`.csv` of `.parquet`)
- `app.py`:
  - `_read_csv_robust()` verwijderd (logica nu in `data_loader.py`)
  - Roept `load_data(input_path)` aan — werkt voor beide formaten
  - Output altijd als `safe_{stem}.csv` opgeslagen, ongeacht het invoerformaat (zodat `/api/download` en `/api/convert` ongewijzigd blijven)
- `index.html`: `accept=".csv"` → `accept=".csv,.parquet"`.

**Waarom:**
Testen of Parquet-input meetbaar sneller is dan CSV bij grotere datasets. De laadtijd is bij 15k rijen klein, maar het maakt de vergelijking mogelijk. CSV blijft ondersteund zodat bestaande workflows niet breken.

**Bronnen:**
- pandas `read_parquet` docs; eigen analyse (stap 27).

**Zelf bedacht:**
Output altijd als CSV — zo werken de download- en converteer-endpoints zonder aanpassingen, ongeacht het invoerformaat.

---

## Stap 31: spaCy-modelkeuze besproken

**Datum:** 2026-04-21

**Prompt (letterlijk):**
> is this the best dataset for the spacy model for presidio? or what can be the difference with another?

**Wat is er gedaan:**
- Huidige modellen geanalyseerd: `nl_core_news_lg` (Nederlands) en `en_core_web_lg` (Engels).
- Voor Nederlands: geen `_trf` (transformer) variant beschikbaar in de standaard spaCy 3.8-releases — `nl_core_news_lg` is het maximum.
- Voor Engels: `en_core_web_trf` (RoBERTa-based) bestaat wel (~90% NER), maar is traag op CPU en levert marginale winst omdat Layer 2 al een transformer runt over wat Layer 1 mist.
- Geen wijzigingen gemaakt.

**Waarom:**
De huidige keuze is de juiste afweging: `_lg` geeft goede nauwkeurigheid bij redelijke snelheid; het meerlaagse ontwerp compenseert structureel wat Layer 1 mist.

**Bronnen:**
- spaCy model-overzicht; eigen analyse van pipeline-architectuur.

**Zelf bedacht:**
Beslissing om `en_core_web_trf` niet te gebruiken — twee transformers in serie (Layer 1 _trf + Layer 2 eu-pii-safeguard) voor marginale winst is niet proportioneel op CPU-hardware.

---

## Stap 32: Layer 2 op GPU gezet

**Datum:** 2026-04-21

**Prompt (letterlijk):**
> why does it run on cpu instead of gpu? my gpu is rtx 4050 so it is stronger

**Wat is er gedaan:**
- Geconstateerd dat `device=-1` hardcoded stond in `layer2_eu_pii.py` (CPU).
- Geconstateerd dat de `privacy-agent` service in `docker-compose.yml` **geen GPU-reservering** had (alleen `ollama` en `vllm` hadden dat).
- `layer2_eu_pii.py`: `device=-1` vervangen door `_device = 0 if torch.cuda.is_available() else -1` — auto-detectie, werkt ook in CPU-omgevingen.
- `docker-compose.yml`: `deploy.resources.reservations.devices` (nvidia, all) toegevoegd aan de `privacy-agent` service.
- Opstartlog toont nu: `Loading tabularisai/eu-pii-safeguard model on GPU (cuda:0)`.

**Waarom:**
Zonder de GPU-reservering in Docker Compose ziet PyTorch de GPU niet, ongeacht wat de code instelt. De RTX 4050 verwerkt BERT-achtige token-classificatie significant sneller dan CPU, vooral met grotere batches.

**Bronnen:**
- Docker Compose `deploy.resources` docs; PyTorch `torch.cuda.is_available()` docs.

**Zelf bedacht:**
Auto-detectie via `torch.cuda.is_available()` i.p.v. een vaste waarde — zo werkt de container ook als iemand zonder GPU draait.

---

## Stap 33: Layer 2 batch-optimalisatie en validatie op 2000 rijen

**Datum:** 2026-04-21

**Prompt (letterlijk):**
> if i use the layer 2 and much data then it does only send a few at a time [...] i think it can be more and faster

**Wat is er gedaan:**
- Geïdentificeerd: `eu_pii_ner(texts)` zonder `batch_size`-parameter gebruikt intern batch_size=1 — de transformer verwerkt teksten één voor één ondanks dat er een lijst meegegeven wordt.
- Fix: `eu_pii_ner(texts, batch_size=len(texts))` — de volledige batch gaat in één transformer forward pass.
- Outer `batch_size` in `process_dataframe_async` verhoogd: 32 → 200 (gebruiker aangepast na testen).
- **Validatieresultaat:** recall op 2000 rijen gelijk aan de resultaten op de kleinere testset — de batching wijzigt de output niet, alleen de snelheid.

**Waarom:**
De HF-pipeline buffert intern niet automatisch; `batch_size` moet expliciet worden meegegeven om de GPU efficiënt te benutten. Zonder dit: 200 afzonderlijke forward passes per batch. Met dit: één forward pass voor 200 teksten tegelijk.

**Bronnen:**
- HF `transformers.pipeline` docs (`batch_size` parameter); eigen loganalyse (eu-pii-safeguard resultaten kwamen in groepjes van ~4 i.p.v. tegelijk).

**Zelf bedacht:**
`batch_size=len(texts)` i.p.v. een vaste waarde — zo schaalt de batch automatisch mee met wat er binnenkomt zonder hardcoded grenzen.

---

## Stap 34: Kolomnamen auto-detecteren bij bestandsupload

**Datum:** 2026-04-22

**Prompt (letterlijk):**
> can you add a option that it detects the top rows of a csv or parquet or jsonl files, i mean the header names? so i can select it in: Column to Anonymize

**Wat is er gedaan:**
- `read_headers(source_path)` toegevoegd aan `data_loader.py`:
  - CSV: `pd.read_csv(path, nrows=0)` — leest alleen de headerrij, geen data geladen
  - Parquet: `pq.read_schema(path).names` — leest schema via pyarrow zonder data te laden
  - Beide formaten verwerkt in dezelfde robuuste encoding/separator-loop als `load_csv`
- Nieuw API-endpoint `POST /api/detect-columns` toegevoegd aan `app.py`:
  - Ontvangt het geüploade bestand, slaat het tijdelijk op, roept `read_headers()` aan, verwijdert het tijdelijke bestand direct daarna
  - Geeft `{"columns": [...]}` terug
- `index.html` bijgewerkt:
  - Bij bestandsselectie wordt direct `POST /api/detect-columns` aangeroepen via fetch
  - Het tekstinvoerveld wordt vervangen door een `<select>` dropdown met de gedetecteerde kolomnamen
  - Veelgebruikte kolomnamen (`feedback_text`, `open antwoord`, `text`, `feedback`) worden automatisch voorgeselecteerd als ze aanwezig zijn
  - Als detectie mislukt blijft het tekstinvoerveld beschikbaar als fallback

**Waarom:**
Bij het testen met verschillende datasets was het telkens handmatig de kolomnaam invullen. De dropdown voorkomt typefouten en maakt het direct duidelijk welke kolommen beschikbaar zijn.

**Bronnen:**
- pandas `read_csv(nrows=0)` docs; pyarrow `read_schema` docs.

**Zelf bedacht:**
Tijdelijk bestand direct verwijderen na headerdetectie zodat de `uploads/`-map niet volloopt bij herhaalde detectie-aanvragen.

---

## Stap 35: Informatieve bestandsnaam op basis van testconfiguratie

**Datum:** 2026-04-22

**Prompt (letterlijk):**
> can you add a option that it detects the top rows... i want that there is a option to convert it... make a service / only do this if i select the recall check

**Wat is er gedaan:**
- `_build_output_filename()` toegevoegd aan `app.py`
- Formaat: `{stem}_L{lagen}[_{model}]_{seconden}s_recall{pct}.csv`
  - Voorbeeld layer 1+2: `test_dataset_v2_L12_23s_recall80.csv`
  - Voorbeeld met layer 3: `test_dataset_v2_L123_Qwen2.5-3B_47s_recall85.csv`
- Naam wordt alleen zo gegenereerd als recall check actief is; anders `safe_{stem}.csv`
- Modelnaam gesaniteerd: slash vervangen, laatste padcomponent, max 20 tekens
- `elapsed_seconds` ook toegevoegd aan de API-response voor weergave in de UI
- Timing meet uitsluitend de verwerkingstijd van `process_dataframe_async` — upload en recall check tellen niet mee

**Waarom:**
Bij benchmarking met meerdere configuraties (laagkeuze, modelkeuze, batchgrootte) was het onmogelijk om achteraf te achterhalen hoe een bestand gegenereerd was. De bestandsnaam bevat nu alle relevante testparameters.

**Bronnen:**
- Eigen ontwerp op basis van benchmarkbehoefte.

**Zelf bedacht:**
Alleen informatieve naam bij recall check — bij productieruns zonder check blijft de simpele `safe_`-naam zodat bestandsbeheer niet complexer wordt.

---

## Stap 36: Testbestand 15.000 rijen gerepareerd

**Datum:** 2026-04-22

**Prompt (letterlijk):**
> & ‘c:\fontys\semester_4\group\agents\privacy_officer\test_dataset_v2 copy 15000.csv’ — fix the file so i can use it

**Wat is er gedaan:**
- Gecorrupte CSV geanalyseerd: bestand had inconsistente quoting (dubbelquotes, gemengde scheidingstekens `;` en `,`) — waarschijnlijk ontstaan door een fout in het kopieerscript.
- Oplossing: clean bestand gegenereerd vanuit het originele `test_dataset_v2.csv` (100 rijen) door het 150× te herhalen:
  ```python
  df = pd.read_csv(‘test_dataset_v2.csv’, sep=’;’)
  big = pd.concat([df] * 150, ignore_index=True)
  big.to_csv(‘test_dataset_v2_15000.csv’, sep=’;’, index=False, encoding=’utf-8-sig’)
  ```
- Output: `test_dataset_v2_15000.csv` — 15.000 rijen, correcte semicolon-delimiter, juiste quoting.

**Waarom:**
Het gecorrupte bestand was onbruikbaar als input voor de anonymizer; pandas kon het niet betrouwbaar parsen.

**Bronnen:**
- Eigen analyse van het bestand; pandas `concat` docs.

**Zelf bedacht:**
Genereren vanuit het origineel is robuuster dan proberen het gecorrupte bestand te repareren — garantie op correcte structuur.

---

## Stap 37: Late masking architectuur — laag 1+2 collecteren, eenmalig masken

**Datum:** 2026-04-22

**Prompt (letterlijk):**
> can it be a higher recall if i change the behavior of the step of mask it, because now it masks at the first layer and then sends the already masked layer to layer two and then it has less context [...] layer 3 has no role now, i not use it now. dont delete it i only disable it. make sure the mask happens at the end

**Architectuurvraag besproken:**
- Huidige aanpak: L1 maskeert → gemaskerde tekst naar L2 → gemaskerde tekst naar L3
- Alternatief: L1 en L2 collecteren spans op de **originele tekst**, eenmalig masken aan het einde
- Conclusie: verbetering mogelijk doordat L2-transformer meer originele context heeft; overlap-resolutie nodig bij gecombineerde spans

**Wat is er gedaan:**

**`layer1_presidio.py`** — nieuw: `collect_presidio_spans(text, config)`:
- Roept `analyzer.analyze()` aan maar slaat `anonymizer.anonymize()` over
- Retourneert `list[(start, end, tag)]` op basis van operators-config

**`layer2_eu_pii.py`** — nieuw: `eu_pii_collect_batch(texts, config)`:
- Roept `eu_pii_ner(texts, batch_size=len(texts))` aan op originele teksten
- Retourneert `list[list[(start, end, tag)]]` per tekst zonder te masken

**`privacy_agent.py`** — nieuw: `apply_all_masks(text, spans)`:
- Overlap-resolutie: **langste span wint** (`docent Smith` klopt `Smith`)
- Vervangingen **van rechts naar links** zodat eerder in de string de offsets geldig blijven
- `anonymize_text_async` en `process_dataframe_async` herschreven: L1+L2 collecteren op originele tekst, spans samenvoegen, eenmalig masken, daarna optioneel L3

**`index.html`** — Layer 3 standaard **uitgevinkt**

**Maskering doet:**
- *Detectie*: Presidio (spaCy + regex) en EU-PII-Safeguard (BERT-transformer)
- *Maskering zelf*: pure Python string-slicing op de samengevoegde spanlijst — geen ML

**Waarom:**
Als L1 `Smith` maskeert naar `[NAME]` ziet L2 een contextverlies rondom die positie. Door beide lagen op de originele tekst te laten detecteren en pas daarna te masken behoudt L2 de volledige context. Verwachte verbetering: 1–3% recall op namen die dichtbij andere geanonimiseerde entiteiten staan.

**Bronnen:**
- Eigen architectuuranalyse; Presidio `RecognizerResult` docs; HF pipeline span-formaat.

**Zelf bedacht:**
Langste span wint als overlap-strategie — consistent met hoe Presidio zelf omgaat met overlappende recognizers. Rechts-naar-links vervangen is de standaardtechniek voor span-vervanging in NLP zonder een aparte offset-tracking.

---

## Stap 38: Batch size in de bestandsnaam

**Datum:** 2026-04-22

**Prompt (letterlijk):**
> it is also good to know of what is the batch size in the name of the file when saving in

**Wat is er gedaan:**
- `batch_size` toegevoegd als parameter aan `_build_output_filename()` in `app.py`
- Formaat uitgebreid: `{stem}_L{lagen}[_{model}]_b{batch_size}_{seconden}s_recall{pct}.csv`
  - Voorbeeld: `test_dataset_v2_15000_L12_b200_47s_recall83.csv`
- `batch_size = 200` als variabele gedefinieerd vóór de `process_dataframe_async`-aanroep en doorgegeven aan zowel de verwerking als de bestandsnaamgeneratie — één plek om te wijzigen

**Waarom:**
Batch size beïnvloedt de doorlooptijd en theoretisch de GPU-bezetting. Voor benchmarking is het relevant om te weten welke batch size bij welke meting hoorde.

**Bronnen:**
- Eigen benchmarkbehoefte.

**Zelf bedacht:**
`batch_size` als lokale variabele i.p.v. hardcoded in de aanroep — zo is één aanpassing voldoende als de waarde verandert.

---

## Stap 39: Oriëntatie op RAG-pipeline — chunking, embedding en vectordatabase

**Datum:** 2026-04-22

**Prompts (letterlijk):**
> if i think about the next step, dont code it, only think. if i have the anominized data in a parquet format and and to chunk the data, after that have a embedding model and a vector database where the chunked data is stored, whats the need of a chunking in parquet if it is placed in a vector database? i want to know what is the benefit of parquet here if the vector database has own data. with the embedding model i want that i can send a question to it and it gives commen chunks back, how does that step work with vector database and embedding? and what is the reason for parquet here?

> why whould i export to parquet then instead of jsonl or csv?

> it has 15 k rows with 8 + questions, so it total there are 120k cells of chunks needed

**Wat is er gedaan:**
Geen code geschreven — denkstap om de RAG-pipeline te begrijpen vóór implementatie.

Drie vragen beantwoord:

1. **Wat doet Parquet in deze pipeline?**
   - Parquet is de *source of truth* van de geanonimiseerde dataset — niet vervangen door de vectordatabase.
   - De vectordatabase slaat alleen vectoren + kleine metadata op. Parquet bewaart alle kolommen en rijen.
   - Bij herindexeren (ander embedding model) herlaad je vanuit Parquet, niet vanuit de vectordatabase.
   - Gestructureerde queries (filter op thema, cursus, datum) doe je op Parquet/DuckDB, niet op een vectordatabase.
   - Parquet = auditeerbaar, afgetekend artefact van de Privacy Officer.

2. **Parquet vs JSONL vs CSV:**
   - JSONL is het meest geschikt voor directe vectordatabase-ingestie: elke regel = één document, metadata als JSON, streaming ingestie mogelijk zonder speciale bibliotheek.
   - CSV is eenvoudig maar heeft geen schemadwang en is trager bij grote datasets.
   - Parquet is optimaal voor kolomgebaseerde analyses op grote datasets, maar vereist pyarrow.
   - Conclusie voor 15k rijen: JSONL is de beste exportkeuze richting de vectordatabase; Parquet blijft als source of truth.

3. **120k chunks — breed naar lang formaat:**
   - 15.000 rijen × 8+ vragen = ~120.000 cellen, elk een afzonderlijk te embedden chunk.
   - De dataset is *wide format* (15k rijen, 8 tekstkolommen). De vectordatabase heeft *long format* nodig: één chunk per record met metadata (row_id, vraagnaam, tekst, thema).
   - De omzetting is een `pandas.melt` ("explode") vóór ingestie.
   - Bij 120k chunks is het knelpunt niet het lezen van het bestand maar het embedden zelf (GPU, batch size, model keuze).
   - Aanbevolen pipeline: `Parquet (wide, 15k) → melt → JSONL (long, 120k) → embedding model → vectordatabase`

**Hoe embedding + vectordatabase retrieval werkt:**
- *Index-fase (eenmalig)*: elke chunk → embedding model → dense vector (bijv. 384 floats) → opgeslagen als `{vector, metadata: {tekst, thema, vraag, row_id}}` in vectordatabase.
- *Query-fase*: gebruikersvraag → zelfde embedding model → query-vector → approximate nearest-neighbor zoekopdracht in vectordatabase → meest gelijkende chunks teruggegeven als context.
- Het embedding model is de brug: zowel chunks als de query gaan door hetzelfde model, zodat vergelijkbare betekenis dicht bij elkaar in de vectorruimte terecht komt.

**Waarom:**
Voordat er gecodeerd wordt is het belangrijk te begrijpen welke rol elk formaat speelt. De keuze tussen Parquet, JSONL en CSV hangt af van het gebruik: analytics vs. ingestie vs. menselijke leesbaarheid. Bij 120k chunks is de datastructuurtransformatie (wide → long) de kritieke stap, niet de bestandsindeling.

**Bronnen:**
- Eigen redenering op basis van bekende eigenschappen van Parquet, JSONL en vectordatabases.

**Zelf bedacht:**
- Het onderscheid tussen Parquet als *source of truth* en JSONL als *ingestie-formaat* — beide hebben een rol, ze vervangen elkaar niet.
- De observatie dat bij 8 vragen per rij de `melt`-stap noodzakelijk is vóór ingestie, en dat dit het eigenlijke architectuurprobleem is, niet de bestandsindeling.

---

## Stap 40: Tekst-normalisatie voor NER — possessive ‘s, ALLCAPS, aanhalingstekens

**Datum:** 2026-04-23

**Prompt (letterlijk):**
*(geen expliciete prompt — probleem ontdekt bij analyse van false negatives na late-masking architectuur)*

**Wat is er gedaan:**
- `_normalize_for_ner(text)` toegevoegd aan zowel `layer1_presidio.py` als `layer2_eu_pii.py`.
- Drie bewerkingen, alle **lengte-bewarend** zodat span-offsets geldig blijven:
  - `"SMITH"` → `"Smith"` (ALLCAPS woord → Title case, zelfde lengte)
  - `"Smith"` → `" Smith "` (aanhalingstekens rondom naam → spaties, zelfde lengte)
  - `Smith’s` → `Smith  ` (possessive `’s` → twee spaties, zelfde lengte)
- `collect_presidio_spans()` en `eu_pii_collect_batch()` passen de normalisatie toe vóór NER-analyse; de originele tekst wordt daarna gebruikt voor maskering — offsets lopen één-op-één.

**Waarom:**
spaCy (Layer 1) en de HF-transformer (Layer 2) herkenden namen in contexten als `"Jansen’s feedback"` niet: het apostrof-s verraadt het NER-model. ALLCAPS-namen (`JANSEN`) werden soms ook gemist. De normalisatie lost dit op zonder de output te veranderen, omdat alleen de analyseinput wordt aangepast.

**Bronnen:**
- Eigen foutanalyse op basis van false negatives bij test_dataset_v2 (namen met possessive en quotes).
- Python `re` docs.

**Zelf bedacht:**
Lengte-bewarende substitutie als vereiste — bij de late-masking architectuur (Stap 37) worden spans op de originele tekst toegepast; als normalisatie de lengte zou wijzigen, slaan de offsets nergens op.

---

## Stap 41: openai/privacy-filter als tweede Layer 2 optie

**Datum:** 2026-04-23

**Prompt (letterlijk):**
*(geen expliciete prompt — eigen onderzoek naar betere Layer 2 NER-modellen)*

**Wat is er gedaan:**

**`layer2_text_norm.py`** — gedeelde normalisatiemodule aangemaakt:
- `normalize_for_ner(text)` geëxtraheerd uit de twee losse `_normalize_for_ner()`-implementaties in Layer 1 en Layer 2 — één centrale plek.

**`layer2_openai_privacy_filter.py`** — nieuw bestand:
- Laadt `openai/privacy-filter` (token-classification, Apache-2.0) via HF `transformers.pipeline`.
- Auto-detectie GPU/CPU via `torch.cuda.is_available()`; optionele FP16 via `LAYER2_FP16` env-var.
- `openai_privacy_filter_collect_batch(texts, config)` — zelfde interface als `eu_pii_collect_batch`: retourneert `list[list[(start, end, tag)]]`.
- Label-mapping: `private_person` → `[NAME]`, `private_address` → `[LOCATION]`, overig → `[PII]`.
- BIOES-prefix stripping (`B-`, `I-`, `E-`, `S-`) voor labels die het model soms retourneert.
- Als het model niet laadt: graceful fallback (leeg spans, geen crash).

**`privacy_agent.py`** — Layer 2 backend selectable:
- `LAYER2_BACKEND_EU_PII = "eu_pii_safeguard"` en `LAYER2_BACKEND_OPF = "openai_privacy_filter"` als constanten.
- `VALID_LAYER2_BACKENDS` set voor validatie.
- `process_dataframe_async()` en `anonymize_text_async()` ontvangen `layer2_backend` parameter; dispatchen naar de juiste collector.

**`app.py`**:
- `layer2_backend: str = Form(LAYER2_BACKEND_EU_PII)` toegevoegd aan `/api/anonymize`.
- Validatie tegen `VALID_LAYER2_BACKENDS`; foutieve waarde geeft `HTTP 400`.
- Layer 2 backend-naam opgenomen in de gegenereerde bestandsnaam (na laag-indicator): `test_dataset_v2_L12_eu_pii_safeguard_b512_47s_recall83.csv`.
- `PIPELINE_BATCH_SIZE` env-var (default 512) als centrale batchgrootte-instelling.

**`index.html`**:
- Dropdown "Layer 2 model" toegevoegd onder Layer 2 checkbox (standaard `eu-pii-safeguard`; optie `openai/privacy-filter`).
- Dropdown disabled als Layer 2 uitgevinkt is.

**Waarom:**
`tabularisai/eu-pii-safeguard` is getraind op Europese PII-patronen maar heeft moeite met sommige Nederlandse namen in feedbackcontext. `openai/privacy-filter` heeft een ander trainingsdomein en kan andere entiteiten oppikken. Door beide beschikbaar te maken kan per dataset getest worden welk model de betere recall geeft zonder codewijzigingen.

**Bronnen:**
- [openai/privacy-filter op Hugging Face](https://huggingface.co/openai/privacy-filter) — Apache-2.0 licentie.
- HF `transformers.pipeline` docs (token-classification, aggregation_strategy).

**Zelf bedacht:**
- `layer2_text_norm.py` als gedeelde module in plaats van duplicatie — consistent met de laagstructuur die in Stap 28 is ingevoerd.
- BIOES-prefix stripping als losstaande helper (`_strip_bioes_prefix`) zodat de tag-mapping leesbaar blijft.
- Graceful fallback als het model niet laadt — de pipeline crasht niet bij een ontbrekend model, maar slaat Layer 2 over.

---

## Stap 42: Entity carry-forward — namen uit één rij meenemen naar andere rijen

**Datum:** 2026-04-24

**Wat is er gedaan:**
- Ontdekt waarom een naam zoals "Smith" in de zin *"received no response from Smith"* niet wordt opgepikt door Layer 1 en Layer 2, terwijl dezelfde naam in andere zinnen wél wordt gedetecteerd.
- Oorzaak: NER-modellen werken per tekst en gebruiken bidirectionele context. "Smith" aan het einde van een zin zonder titel, voornaam of andere namen in de buurt valt onder de drempelwaarde van spaCy. Layer 2 krijgt daarna al een `[PII]`-placeholder in de tekst, wat de grammaticale context verder verstoort.
- `_build_carryforward_spans(texts, all_raw_spans)` geïmplementeerd in `privacy_agent.py`:
  - Verzamelt alle unieke `[NAME]`-strings (≥ 3 tekens) uit de spans van alle rijen in de batch.
  - Zoekt voor elke rij via regex (`\bNaam\b`, case-insensitief) naar voorkomens van bekende namen die nog niet gedekt zijn door een bestaande span.
  - Retourneert extra spans die worden samengevoegd met de Layer 1+2 spans vóór de maskeerstap.
- `_process_chunk_sync` aangepast: bouwt eerst `combined` spans (L1 + L2), roept dan `_build_carryforward_spans` aan, en geeft alle spans samen door aan `apply_all_masks`.

**Waarom:**
Als "Smith" in rij 3 wordt gevonden maar niet in rij 7, is er geen reden aan te nemen dat het in rij 7 geen persoonsnaam is — het is dezelfde dataset. Het carry-forward mechanisme hergebruikt bestaande detecties zonder extra model-aanroepen. Prestatieimpact is verwaarloosbaar: alleen regex-zoekacties over al berekende spans.

**Bronnen:**
- Eigen analyse van waarom NER context-afhankelijk is en waarom `[PII]`-placeholders de volgende laag benadelen.
- Python `re`-module voor `\b`-woordgrenspatronen.

**Zelf bedacht:**
Eigen idee na gebruikersvraag: "als Smith in één zin gevonden wordt, waarom wordt het niet overgenomen naar andere zinnen?". Geen tutorial gevolgd — directe vertaling van het probleem naar een batch-brede namenset met regex carry-forward.

**Resultaat:**
Smith wordt verwijderd uit de tekst.
---

## Snelle commando’s (hergebruik)

```text
# Stack met Ollama + privacy-agent (projectmap)
docker compose pull ollama
docker compose up --build -d

# Model in Ollama-container
docker compose exec ollama ollama pull gemma4:e4b

# Logs
docker compose logs -f privacy-agent
docker compose logs -f ollama

# Actieve OLLAMA_NUM_PARALLEL in draaiende container (staat niet in elke GIN-regel)
docker compose exec ollama env | findstr OLLAMA_NUM
```

---

## Open punten / vervolg

- Bij veel **false positives** (bijv. `C++`, kleuren): prompt scherper stellen of categories in UI beperken — los van Docker.
- **vLLM** alleen nodig als `LLM_BACKEND=vllm`: `docker compose --profile vllm up -d` (en geen dubbele GPU-belasting met Ollama als beide niet nodig zijn).
