# Decision Log - Privacy Officer Agent

**Naam:** Nick van Hooff
**Klas:** MA-AAI1
**Rol:** GenAI Engineer

---

## Entry #1: Architectuurkeuze voor PII-anonimisering

### Onderzoeksvraag

> Welke opbouw van het systeem haalt Nederlandse studentfeedback het meest betrouwbaar leeg van PII, en hoe verdeel ik de verantwoordelijkheid voor verschillende soorten PII het best over de beschikbare tools, rekening houdend met snelheid, AVG-compliance en controleerbaarheid?

---

### 1. Context

**Project:** Privacy Officer Agent, Groepsproject Fontys Semester 4

**Waarom dit nu belangrijk is:**
De eerste versie werkte alleen met een lokaal LLM (llama3.2:3b via Ollama). Bij tests bleek dat het model e-mailadressen, telefoonnummers en studentnummers niet altijd eruit haalde, afhankelijk van hoe de zin geschreven was. Dat is een probleem: als er ook maar één e-mailadres doorheen glipt, is er al een **AVG-overtreding**. Zonder een goede architectuurkeuze kan ik de rest van het systeem niet bouwen. Ik moest eerst weten welke aanpak de juiste is voordat ik verder kon.

**Link naar opdracht:**
[# NSE Open Response Analysis with AI](https://fhict.instructure.com/courses/15749/pages/nse-open-response-analysis-with-ai?module_item_id=1406608)

**Deelvraag:**
Is een pure LLM-aanpak voldoende voor het anonimiseren van gestructureerde PII, of is een gelaagde aanpak met deterministische tooling betrouwbaarder?

**Projectbriefing:** De Privacy Officer Agent moet Nederlandse studentfeedback automatisch anonimiseren zodat docenten en coördinatoren er veilig mee kunnen werken. Alles draait volledig lokaal, er gaat geen data naar buiten.

**Huidige LO-fase:**
- [x] Analyseren
- [x] Adviseren
- [x] Ontwerpen
- [ ] Realiseren
- [ ] Beheren

---

### 2. Succescriteria

Bij het kiezen van deze criteria wilde ik niet alleen dat het systeem "werkt", maar dat het ook aantoonbaar betrouwbaar is. Eén gemiste e-mailadres is al een juridisch probleem. Daarom heb ik criteria gekozen die echt meten wat ertoe doet: recall op gevaarlijke PII, snelheid voor dagelijks gebruik, en deterministisch gedrag zodat ik het systeem kan verdedigen tegenover een Data Protection Officer.

| Criterium                      | Doel                                                                                                                        |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| **Recall gestructureerde PII** | >= 98%, e-mails, telefoonnummers en studentnummers mogen bijna nooit doorgelaten worden                                    |
| **Snelheid**                   | 500 rijen verwerken in <= 15 minuten; langer is onwerkbaar in de praktijk                                                   |
| **Deterministisch**            | Hetzelfde bestand twee keer door het systeem = identieke output. Een LLM dat elke keer anders beslist is niet te verdedigen |
| **Indirecte PII**              | Omschrijvingen als "de docent met de kale kop" worden vervangen door een placeholder én gevlagd voor review. Wat de juiste placeholder moet zijn wordt nog onderzocht; hiervoor wachten we op een interview met de kwaliteitsmedewerkers die de data analyseren. |

---

### 3. Beslissing

**Gekozen: drie-lagen architectuur**

Ik heb besloten om een systeem te bouwen waarbij elke laag een specifieke klasse van PII aanpakt die de vorige laag niet goed aankan. Een pure LLM-aanpak is niet geschikt voor gestructureerde PII: te wisselend en niet controleerbaar. Door Presidio en eu-pii-safeguard vooraan te zetten pakt elke tool de PII-categorie aan waarvoor die gemaakt is. Het LLM behandelt alleen wat overblijft.

**Laag 1: Microsoft Presidio**
Presidio gebruikt vaste regels en **Named Entity Recognition** voor het herkennen van structurele PII: e-mailadressen, telefoonnummers, studentnummers (via eigen regex-herkenner), namen en locaties die duidelijk benoemd zijn, en ook gespelde e-mails zoals "x punt y apenstaartje gmail punt com". Volledig **deterministisch** en draait offline. Heeft de Nederlandse en Engelse **spaCy**-taalmodellen nodig om Nederlandse tekst correct te parsen.

**Laag 2: tabularisai/eu-pii-safeguard**
eu-pii-safeguard is een AI-model gebaseerd op **XLM-RoBERTa-large**, specifiek getraind voor Europese persoonsgegevens. Het herkent 42 soorten PII in alle 26 officiële EU-talen, inclusief Nederlands, en vult de gaten die Presidio laat liggen. De zelfgerapporteerde F1-score is **97.02%** (Precision 97.0%, Recall 97.0%) (1). Het model werkt **deterministisch**, draait offline en zonder API-kosten.

**Laag 3: Aya Expanse 8b via Ollama**
Aya Expanse 8b is een LLM dat indirecte en omschrijvende PII aanpakt die geen enkel NER-model aankan, zoals "de enige vrouw in het ICT-team" of "de man met de rode jas die altijd te laat komt". Of dit de definitieve keuze is staat nog open, de kwaliteit versus snelheid-afweging wordt verder onderzocht.

**Extra functionaliteit:**
- **Lagen aan/uit zetten:** Via de UI kun je per checkbox kiezen welke lagen draaien. Zo is direct vergelijkbaar wat elke laag bijdraagt aan kwaliteit en snelheid. Zonder laag 3 gaat verwerking van 100 rijen van 1-1,5 minuut terug naar enkele seconden.
- **PII-categorieën selecteren:** Per type (namen, locaties, studentnummers, vakken, fysieke omschrijvingen, e-mail/telefoon) kies je of het eruit gehaald wordt of niet.
- **Docker deployment:** Alles draait via **Docker Compose** zodat het systeem zonder handmatige installatie op andere machines kan draaien.

---

### 3b. Gebruikte AI-tools bij het bouwen van het prototype

Bij het bouwen van dit prototype heb ik bewust meerdere AI-tools ingezet voor verschillende onderdelen. Ik vind het belangrijk om dit transparant te vermelden, ook omdat het laat zien hoe je als engineer AI-agents effectief kunt inzetten als onderdeel van je werkproces.

**Antigravity (met Anthropic-modellen)**
Gebruikt voor de initiële projectopzet. De basisstructuur van het project inclusief de koppeling met Anthropic-modellen is hiermee opgezet.

**Claude Code**
Gebruikt voor aanpassingen en uitbreidingen aan de bestaande code, zoals de PII-categorieselectie in de UI (de checkboxes waarmee je per type kunt kiezen wat eruit gehaald wordt) en de laag-toggles. Daarnaast heeft Claude Code het architectuuronderzoek gedaan dat gedocumenteerd staat in [PII_ARCHITECTURE_DISCUSSION.md](https://github.com/nickvanhooff/agents/blob/main/privacy_officer/PII_ARCHITECTURE_DISCUSSION.md).

**Cursor (met Claude Sonnet 4.5)**
Gebruikt voor het analyseren van de CSV-testbestanden. De rij-voor-rij analyse van de testresultaten per laag is door Cursor gegenereerd op basis van de ruwe outputdata. De resultaten staan in [LAYER_ANALYSIS.md (Aya 8b)](https://github.com/nickvanhooff/agents/blob/main/privacy_officer/data_with_testing_layers_Presidio_eu-pii-safeguard_aya/LAYER_ANALYSIS.md) en [LAYER_ANALYSIS_llama3.2-3b.md](https://github.com/nickvanhooff/agents/blob/main/privacy_officer/data_with_testing_layers_Presidio_eu-pii-safeguard_llama3.2-3b/LAYER_ANALYSIS_llama3.2-3b.md).

**Gemini**
Gebruikt voor het zoeken naar geschikte HuggingFace-modellen voor de PII-detectie, waaronder eu-pii-safeguard.

**Eigen keuzes en ideeën**
De technische keuzes voor de opzet waren mijn eigen beslissingen: Docker als deployment-methode zodat het systeem zonder handmatige installatie overdraagbaar is, FastAPI als backend en een eenvoudig HTML-bestand als UI. De drie-lagen architectuurgedachte en de keuze om lagen en PII-categorieën selecteerbaar te maken zijn ook eigen ideeën.

---

### 4. Onderzoeksmethode (DOT-framework)

Om tot deze beslissing te komen, heb ik de volgende DOT-methoden toegepast:

**Literatuuronderzoek & productvergelijking (Library)**
Tijdens het lezen van documentatie werden tools direct met elkaar vergeleken. Model cards, officiële documentatie en technische beschrijvingen van Presidio, eu-pii-safeguard en Aya Expanse doorgenomen. De zelfgerapporteerde evaluatiecijfers van eu-pii-safeguard (F1: **97.02%**) (1) zijn genoteerd en beoordeeld op betrouwbaarheid. Beschikbare tools vervolgens systematisch vergeleken op: ondersteunde PII-types, talen, lokaal draaien, snelheid, en of het gedrag **deterministisch** is. Conclusie: geen enkele tool dekt alle PII-types, vandaar de gelaagde aanpak.

**Ontwerp & iteratief bouwen (Workshop)**
De vier succescriteria (recall, snelheid, determinisme, AVG-compliance) als **scoringskader** gebruikt om te bepalen welke tool welke laag invult. Daarna elke laag los gebouwd en stap voor stap samengevoegd: begin met alleen LLM, daarna Presidio toegevoegd, daarna eu-pii-safeguard. Na elke stap gecontroleerd of de kwaliteit verbeterde.

**Testen & modelkwaliteit (Lab)**
Elke laag afzonderlijk getest op zelf gegenereerde testfeedback met bekende PII. De resultaten per laag vertaald naar bruikbare bevindingen. Gecontroleerd of de testdata voldoende dekking biedt om conclusies op te baseren (4). Drie opeenvolgende runs vergeleken om te bevestigen of laag 1 en 2 deterministisch zijn (3).

**Prestatiemeting (Showroom)**
Verwerkingstijd gemeten per laag en voor de volledige pipeline op concrete input: 100 rijen tekst op een laptop met 32GB RAM en een NVIDIA GPU met 6GB VRAM, via Docker met NVIDIA Container Toolkit actief. Resultaat: **1-1,5 minuut** met alle drie de lagen; enkele seconden zonder laag 3.

---

### 5. Bevindingen

**Testomgeving:** Laptop met 32GB RAM, NVIDIA GPU met 6GB VRAM, Docker Compose met NVIDIA Container Toolkit actief
**Testdata:** `safe_student_feedback - extreme.csv` met **13 rijen** opzettelijk uitdagende Nederlands/Engelse studentfeedback met bekende PII. Het plan was om 100 rijen te testen, maar voor deze eerste meting heb ik bewust 13 rijen gebruikt om snel per laag te kunnen vergelijken. Een volledige 100-rijen test volgt in de volgende fase.
**Bron tijden:** [LAYER_ANALYSIS.md (Aya 8b)](https://github.com/nickvanhooff/agents/blob/main/privacy_officer/data_with_testing_layers_Presidio_eu-pii-safeguard_aya/LAYER_ANALYSIS.md) en [LAYER_ANALYSIS_llama3.2-3b.md](https://github.com/nickvanhooff/agents/blob/main/privacy_officer/data_with_testing_layers_Presidio_eu-pii-safeguard_llama3.2-3b/LAYER_ANALYSIS_llama3.2-3b.md)

| Configuratie | Totale tijd (13 rijen) | Per rij | Schatting 500 rijen |
|---|---|---|---|
| **Laag 1 alleen (Presidio)** | ca. 0.25s | ca. 0.02s | ca. 10s |
| **Laag 2 alleen (EU-PII)** | ca. 1.4s | ca. 0.11s | ca. 55s |
| **Laag 1 + 2** | ca. 1.6s | ca. 0.12s | ca. 60s |
| **Alle lagen met Aya Expanse 8b** | ca. 1:41 min | ca. 7.8s | ca. 65 min |
| **Alle lagen met Llama 3.2 3b** | ca. 30s | ca. 2.3s | ca. 19 min |
| **Laag 3 alleen met Llama 3.2 3b** | ca. 28s | ca. 2.2s | ca. 18 min |

**Wat de test liet zien per laag:**
- **Laag 1 (Presidio):** Pakt e-mail, telefoon, namen en locaties goed op. Mist "mevrouw de jong" (titel + achternaam zonder hoofdletter), "piet jansen" (lowercase) en medische termen zoals ADHD. Vangt als enige gespelde e-mails op via custom regex ("s punt van_der_meer apenstaartje…"). Snelheid: verwaarloosbaar (ca. 0.02s/rij). Bron: [LAYER_ANALYSIS.md](https://github.com/nickvanhooff/agents/blob/main/privacy_officer/data_with_testing_layers_Presidio_eu-pii-safeguard_aya/LAYER_ANALYSIS.md)
- **Laag 2 (EU-PII-Safeguard):** Pakt ADHD op als medische PII, iets wat Presidio en het LLM allebei missen. Mist echter veel Nederlandse namen (Roos, Jasmijn, Sjaak, Pietersen). Heeft tokenizer-bugs als het alleen draait: gedeeltelijke vervangingen ("de v[NAME]s"), dubbele tags ("[LOCATION][LOCATION]"). Nooit los gebruiken. Bron: [LAYER_ANALYSIS.md](https://github.com/nickvanhooff/agents/blob/main/privacy_officer/data_with_testing_layers_Presidio_eu-pii-safeguard_aya/LAYER_ANALYSIS.md)
- **Laag 3 (Aya 8b vs Llama 3.2 3b):** Beide modellen zijn de enige die fysieke beschrijvingen ("kale docent", "rode bril"), "mevrouw de jong" en contextuele verwijzingen ("blauwe Porsche", "mijn mentor") oppakken. Aya 8b is consistenter en doet het beter op Nederlandse nuances; Llama 3.2 3b is **ca. 3.4x sneller** (2.3s vs 7.8s/rij) maar heeft meer artefacten (dubbele tags, verkeerde labels). Bron: [LAYER_ANALYSIS_llama3.2-3b.md](https://github.com/nickvanhooff/agents/blob/main/privacy_officer/data_with_testing_layers_Presidio_eu-pii-safeguard_llama3.2-3b/LAYER_ANALYSIS_llama3.2-3b.md)
- **Presidio + EU-PII bovenop Llama 3.2 3b:** Kost bijna geen extra tijd (+2s op 13 rijen). Je krijgt de veiligheid van deterministische lagen er dus vrijwel gratis bij als je toch Llama gebruikt.
- **Over-anonimisering:** Laag 3 verwijdert soms te veel. Zo worden "semester 4" en "project" in sommige rijen ook vervangen en wordt "digibord" in de volledige pipeline vervangen terwijl dat geen PII is.

**Wat me verraste:**
Presidio vereist de juiste spaCy-taalmodellen; zonder `nl_core_news_lg` gooit het systeem een foutmelding bij het verwerken van Nederlandse tekst. Nog verrassender was dat Docker de NVIDIA GPU **standaard niet** gebruikt. De NVIDIA Container Toolkit was nergens duidelijk vermeld als vereiste in de Presidio of Ollama documentatie. Na installatie was het effect op verwerkingstijd direct zichtbaar. Daarnaast is de standaard PyTorch-installatie enorm groot door alle meegeleverde CUDA-bibliotheken; een CPU-only build is kleiner maar merkbaar langzamer.

**Conclusie:** De drie-lagen opbouw verdeelt het werk op basis van wat elke tool aankan: **deterministische tooling** voor expliciete PII, semantisch redeneren alleen voor de moeilijkste gevallen. Voor 500 rijen is Aya 8b met alle lagen te langzaam (ca. 65 min); Llama 3.2 3b (ca. 19 min) zit ook boven de grens van 15 minuten. Alleen laag 1+2 haalt het snelheidscriterium makkelijk, maar mist dan indirecte PII.

---

### 6. Validatie succescriteria

| Criterium                      | Doel                              | Resultaat                                                                                                                                                                                                                                                                                                            | Gehaald?         |
| ------------------------------ | --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------- |
| **Recall gestructureerde PII** | >= 98%                            | Presidio + eu-pii-safeguard haalt e-mail, telefoon en studentnummers vrijwel foutloos eruit in handmatige controle op eigen testdata. Formele meting op gelabelde studentfeedback nog niet gedaan.                                                                                                                   | ✅ (streefwaarde) |
| **Snelheid**                   | <= 15 min voor 500 rijen          | Laag 1+2: ca. 60s voor 500 rijen ✅. Alle lagen + Aya 8b: ca. 65 min ❌. Alle lagen + Llama 3.2 3b: ca. 19 min ❌. Gemeten op 13 testrows (ca. 7.8s/rij Aya, ca. 2.3s/rij Llama). Bron: LAYER_ANALYSIS.md                                                                                                               | 🟡 Deels         |
| **Deterministisch**            | Identieke output bij herhaling    | Laag 1 en 2 bevestigd via drie opeenvolgende runs op dezelfde input. Laag 3 (LLM) is bewust niet deterministisch; het staat als laatste laag voor de moeilijkste gevallen                                                                                                                                            | ✅                |
| **Indirecte PII**              | Placeholder + gevlagd voor review | LLM vervangt een deel al met een placeholder en markeert de rij. Bij subtiele omschrijvingen schiet het model tekort, menselijke controle blijft nodig. Wat de juiste placeholder per type moet zijn is nog niet bepaald; dit wordt onderzocht via een interview met de kwaliteitsmedewerkers die de data gebruiken. | 🟡 Deels         |

**Recall:** Presidio + eu-pii-safeguard haalt gestructureerde PII vrijwel foutloos eruit in handmatige controle op eigen testdata. De 98% is een **streefwaarde**, geen gemeten resultaat op echte studentfeedback. Dat is de volgende stap.

**Snelheid:** De test was op **13 rijen** uit `safe_student_feedback - extreme.csv`. Laag 1+2 is razendsnel (ca. 0.12s/rij, ca. 60s voor 500 rijen). Maar zodra laag 3 erbij komt, domineert het LLM de verwerkingstijd volledig: Aya 8b zit op ca. 7.8s/rij (ca. 65 min voor 500 rijen) en Llama 3.2 3b op ca. 2.3s/rij (ca. 19 min). Het snelheidscriterium van 15 minuten wordt alleen gehaald als laag 3 uitstaat, of als er een sneller model gevonden wordt. Dit is een open punt voor het vervolgonderzoek.

**Determinisme:** Laag 1 en 2 geven identieke output bij drie opeenvolgende runs. Laag 3 niet, maar dat is ook logisch want het LLM redeneert contextafhankelijk. Die variabiliteit is acceptabel voor indirecte PII waar menselijke review toch al vereist is.

**Indirecte PII:** Het systeem vervangt indirecte PII al met een placeholder én zet de rij in de reviewwachtrij. Maar welke placeholder het meest bruikbaar is voor de kwaliteitsmedewerkers die de data analyseren, dat weten we nog niet. Te specifiek (`[FYSIEKE_BESCHRIJVING]`) of te generiek (`[PII]`) maakt allebei de output minder bruikbaar. Hiervoor wachten we op een interview met die medewerkers voordat we dit criterium als gehaald kunnen afvinken.

---

### 7. Aannames

- De gecombineerde recall van Presidio + eu-pii-safeguard is hoger dan 95% op directe PII. Gebaseerd op de **zelfgerapporteerde** F1-score van **97.02%** van eu-pii-safeguard (1) en handmatige controle op eigen testdata. Geen formele meting op echte studentfeedback.
- Indirecte PII maakt een klein deel van de teksten uit. Als dit groter uitvalt dan verwacht, is laag 3 mogelijk een knelpunt voor de verwerkingstijd.
- Presidio herkent de taal automatisch en schakelt tussen Nederlands en Engels. Dat werkt in de praktijk goed, maar kan falen bij gemengde zinnen.

---

### 8. Bronnen

**(1)** Tabularisai. (2024). *EU-PII-Safeguard* [Model Card]. Hugging Face.
https://huggingface.co/tabularisai/eu-pii-safeguard
Geraadpleegd: maart 2025. Gebruikte data: F1-score (97.02%), Precision (97.0%), Recall (97.0%), 42 PII-types, 26 EU-talen, modelarchitectuur (XLM-RoBERTa-large, 0.6B parameters). Kanttekening: zelfgerapporteerde evaluatiecijfers; de testdataset is niet publiek beschikbaar.

**(2)** Microsoft. (z.d.). *Presidio: Data Protection and De-identification SDK*. GitHub Pages.
https://microsoft.github.io/presidio/
Geraadpleegd: maart 2025. Gebruikte data: architectuur analyzer/anonymizer, spaCy-integratie, ondersteunde entiteitstypen.

**(3)** HBO-i. (z.d.). *Model Validation (ML)*. ICT Research Methods.
https://ictresearchmethods.nl/lab/model-validation/
Geraadpleegd: maart 2025. Gebruikt als referentie voor het toepassen van model validation als DOT-onderzoeksmethode.

**(4)** HBO-i. (z.d.). *Data Quality Check (ML)*. ICT Research Methods.
https://ictresearchmethods.nl/lab/data-quality-check/
Geraadpleegd: maart 2025. Gebruikt als referentie voor het toepassen van data quality check als DOT-onderzoeksmethode.

---

### 9. Implementatiebewijs

| Bestand                                                                                                                                                                                        | Wat het bewijst                                                                             |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| [privacy_agent.py](https://github.com/nickvanhooff/agents/blob/main/privacy_officer/src/core/privacy_agent.py)                                                                                 | Drie-lagen logica, layer-toggles, categorie-config                                          |
| [PII_ARCHITECTURE_DISCUSSION.md](https://github.com/nickvanhooff/agents/blob/main/privacy_officer/PII_ARCHITECTURE_DISCUSSION.md)                                                              | Modelvergelijking en architectuuronderbouwing                                               |
| [docker-compose.yml](https://github.com/nickvanhooff/agents/blob/main/privacy_officer/docker-compose.yml)                                                                                      | GPU-configuratie via NVIDIA device reservation                                              |
| [create_dummy_data.py](https://github.com/nickvanhooff/agents/blob/main/privacy_officer/scripts/create_dummy_data.py)                                                                          | Testdata met bekende PII voor data quality check                                            |
| [ollama_entrypoint.sh](https://github.com/nickvanhooff/agents/blob/main/privacy_officer/scripts/ollama_entrypoint.sh)                                                                          | Automatisch ophalen van aya-expanse:8b bij opstarten                                        |
| [TESTING_CONCLUSION.md](https://github.com/nickvanhooff/agents/blob/main/privacy_officer/TESTING_CONCLUSION.md)                                                                                | Snelheidsbenchmarks en layer coverage matrix, onderbouwing van de getallen in sectie 5 en 6 |
| [LAYER_ANALYSIS.md (Aya 8b)](https://github.com/nickvanhooff/agents/blob/main/privacy_officer/data_with_testing_layers_Presidio_eu-pii-safeguard_aya/LAYER_ANALYSIS.md)                        | Rij-voor-rij testresultaten per laag met Aya Expanse 8b                                     |
| [LAYER_ANALYSIS_llama3.2-3b.md](https://github.com/nickvanhooff/agents/blob/main/privacy_officer/data_with_testing_layers_Presidio_eu-pii-safeguard_llama3.2-3b/LAYER_ANALYSIS_llama3.2-3b.md) | Rij-voor-rij testresultaten per laag met Llama 3.2 3b                                       |

---

### 10. Volgende stappen

**Volgende LO-fase:** Realiseren

De architectuur staat en werkt. Nu kan ik een CSV met Nederlandse studentfeedback invoeren, per laag en per PII-categorie kiezen wat eruit gehaald wordt, en direct vergelijken wat het verschil is in kwaliteit en snelheid. Alle verwerking gebeurt **lokaal via Docker**, er gaat niets naar buiten.

De volgende stap is recall formeel meten op gelabelde data en onderzoeken of laag 3 beter kan of vervangen moet worden door een ander model. Het grotere Aya Expanse 8b model presteert beter dan 3b, maar is ook langzamer. Die afweging wil ik onderbouwen met echte metingen.

**Definitie of Done:**
Ik weet dat deze keuze de juiste was als ik 50 handmatig gelabelde testregels door de volledige pipeline kan sturen en >= **98% recall** op gestructureerde PII haal voor laag 1+2 samen. Daarnaast moeten drie opeenvolgende runs op dezelfde input voor laag 1 en 2 identieke output geven als bewijs van determinisme. Als dat lukt, heb ik een werkende basis die ik aan het team en aan de opdrachtgever kan laten zien.

---

## Begrippenlijst

### PII: Persoonsgegevens

PII staat voor Personally Identifiable Information, ofwel persoonsgegevens. Dit zijn alle gegevens die **direct** of **indirect** herleid kunnen worden naar een specifiek persoon. Voorbeelden van directe PII zijn namen, e-mailadressen, telefoonnummers en studentnummers. Indirecte PII zijn omschrijvingen die in combinatie identificerend zijn, zoals "de enige vrouw in het ICT-team". In Nederland en Europa valt PII onder de AVG (Algemene Verordening Gegevensbescherming), ook bekend als de GDPR.

### Recall

Recall geeft aan welk percentage van alle PII die echt in de tekst staat gevonden is door het systeem. Voorbeeld: als er 10 stukjes PII in een tekst staan en het systeem vindt er 9, is de **recall** 90%. Het gemiste geval heet een **false negative**. Voor een anonimiseringssysteem is recall de meest kritische maatstaf, want een enkel gemist e-mailadres kan al een AVG-overtreding zijn.

### Precision

Precision geeft aan welk percentage van alles wat het systeem als PII markeert ook echt PII is. Een lage precision betekent veel **vals alarm**: het systeem haalt te veel eruit wat geen PII is. Voor anonimisering is precision minder kritisch dan recall, maar een te lage precision maakt de output onleesbaar.

### F1-score

De **F1-score** combineert precision en recall in een enkel getal. Een score van 100% betekent dat het model alles correct vindt zonder vals alarm te slaan. In de praktijk geldt alles boven 90% als goed en boven 95% als zeer goed voor NLP-taken. Belangrijk: een hoge F1-score garandeert niet dat het model goed werkt op jouw specifieke data, het is altijd een gemiddelde over een testset.
