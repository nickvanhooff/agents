# 🏗️ Fontys Privacy Officer Agent - Architecture Diagram

Dit diagram toont de stroom van data en communicatie tussen alle componenten van de Privacy Officer applicatie. Dit is ideaal om aan de IT-architect van Fontys te laten zien, zodat zij direct begrijpen dat **alles lokaal blijft** en de NDA gewaarborgd is.

Je kunt de onderstaande Mermaid-code kopiëren en in een tool zoals [Mermaid Live Editor](https://mermaid.live/) of in jullie eigen documentatie plakken.

```mermaid
sequenceDiagram
    autonumber
    actor Gebruiker as Fontys Medewerker
    box LightBlue Lokale Machine / Server
        participant UI as Web Interface (HTML/JS)
        participant API as FastAPI Backend (app.py)
        participant Core as Privacy Agent (privacy_agent.py)
        participant Presidio as Layer 1: Presidio
        participant EUPII as Layer 2: EU-PII-Safeguard
        participant Ollama as Layer 3: Ollama (aya-expanse:8b)
    end
    
    note over Gebruiker, Ollama: Volledig offline, geen cloud of internet verbinding

    Gebruiker->>UI: Uploadt raw CSV, kiest kolom, lagen en entiteit-types
    UI->>API: HTTP POST /api/anonymize (Multipart Form Data)
    
    activate API
    API->>API: Slaat .csv lokaal op in /uploads/raw_*.csv
    API->>Core: process_dataframe(df, text_column, config, layers)
    
    activate Core
    loop Elke rij in de gekozen kolom
        Core->>Presidio: Layer 1: NER + regex (PERSON, EMAIL, LOCATION, STUDENT_NUMBER)
        Presidio-->>Core: Tekst met [NAME], [PII], [LOCATION] tags
        
        Core->>EUPII: Layer 2: Transformer (tabularisai/eu-pii-safeguard)
        EUPII-->>Core: Extra entiteiten gemaskeerd
        
        Core->>Ollama: Layer 3: JSON-extractie prompt (contextuele PII)
        activate Ollama
        Ollama-->>Core: JSON met namen, titels, cursussen, fysieke beschrijvingen
        deactivate Ollama
        
        Core->>Core: Vervangt entiteiten, valideert output
    end
    
    Core-->>API: Retourneert veilige Pandas DataFrame
    deactivate Core
    
    API->>API: Slaat veilige DataFrame op als /uploads/safe_*.csv
    API-->>UI: JSON { success, download_url, flagged_count }
    deactivate API
    
    UI-->>Gebruiker: Toont succesmelding en download link
    Gebruiker->>UI: Klikt "Download"
    UI->>API: HTTP GET /api/download/safe_*.csv
    API-->>Gebruiker: Veilige CSV File
```

### 🧩 Componenten Uitleg:
1. **Web Interface (HTML/JS)**: De gebruiksvriendelijke "voorkant" die in de browser draait. Bevat checkboxes voor lagen (1–3) en entiteit-types (namen, locaties, PII, titels, etc.).
2. **FastAPI Backend** ([privacy_officer/src/api/app.py](privacy_officer/src/api/app.py)): Ontvangt het bestand, valideert layer-selectie, roept de core aan, en regelt downloads. Biedt SSE voor real-time voortgang.
3. **Privacy Agent** ([privacy_officer/src/core/privacy_agent.py](privacy_officer/src/core/privacy_agent.py)): Triple-layer pipeline. Layer 1: Presidio (regex/NER). Layer 2: EU-PII-Safeguard (transformer). Layer 3: Ollama LLM (contextueel). Lagen zijn selecteerbaar via de UI.
4. **Ollama Service**: Lokaal AI-model (standaard `aya-expanse:8b`). Luistert op poort `11434`. Omdat het **niet** in de cloud draait, lekt er geen data.


---

## 🏛️ C4 Container Diagram

Dit is een Niveau 2 (Container) C4-diagram dat perfect aantoont hoe de systemen van elkaar geïsoleerd zijn. De grijze rand ("System_Boundary") maakt direct duidelijk dat de hele oplossing binnen de beveiligde IT-infrastructuur van Fontys kan draaien.

```mermaid
C4Container
    title Container diagram voor het Fontys Privacy Officer Systeem

    Person(medewerker, "Fontys Kwaliteitsmedewerker", "Uploadt NSE data, kiest lagen en entiteit-types, downloadt geanonimiseerde resultaten.")

    System_Boundary(c1, "Privacy Officer Agent (Lokale Omgeving)") {
        Container(spa, "Web Interface", "HTML, CSS, JavaScript", "Upload, kolomnaam, layer-checkboxes (1–3), entiteit-types.")
        Container(api, "Privacy API App", "Python, FastAPI", "Verwerkt uploads, valideert layers, orkestreert pipeline, SSE voortgang, downloads.")
        Container(agent, "Core Privacy Logic", "Python, Presidio, Transformers, Pandas", "Triple-layer pipeline: (1) Presidio NER+regex, (2) EU-PII-Safeguard transformer, (3) Ollama LLM. Lagen selecteerbaar.")
        Container(llm, "Ollama Service", "Ollama (aya-expanse:8b)", "Layer 3: Lokaal LLM voor contextuele PII-extractie.")
        
        ContainerDb(fs, "Local File System", "Uploads Map", "raw_*.csv en safe_*.csv")
    }

    Rel(medewerker, spa, "Bezoekt", "Webbrowser (http://localhost:8000)")
    Rel(spa, api, "Maakt API calls", "Multipart Form + SSE")
    Rel(api, fs, "Slaat op / Leest", "Lokale Bestands-I/O")
    Rel(api, agent, "Roept aan", "process_dataframe(df, text_column, config, layers)")
    Rel(agent, llm, "Layer 3: JSON-extractie", "HTTP POST (localhost:11434)")
    Rel(llm, agent, "Retourneert JSON", "Extracted entities")
```

---

## 🧩 C4 Component Diagram (Level 3)

Dit is een Niveau 3 (Component) C4-diagram dat inzoomt in de "Privacy API App" en "Core Privacy Logic" containers om te laten zien hoe de Python code intern in elkaar steekt. Dit is nuttig voor developers om te begrijpen hoe applicatie componenten samenwerken.

```mermaid
C4Component
    title Component diagram voor de Privacy Officer API en Core Logic

    Container(spa, "Web Interface", "HTML/JS", "Upload, kolomnaam, layer-checkboxes (1–3), entiteit-types.")
    Container(fs, "Local File System", "Uploads Map", "/uploads/")
    Container(llm, "Ollama Service", "aya-expanse:8b", "Layer 3: contextuele PII-extractie")

    Container_Boundary(api, "Privacy API App (app.py)") {
        Component(router_ui, "UI Router", "FastAPI Route", "Serveert index.html op '/'")
        Component(router_api, "API Router", "FastAPI Route", "POST /api/anonymize, GET /api/progress (SSE), GET /api/download")
        Component(file_handler, "File Handler", "Python File I/O", "Slaat raw_*.csv op, leest CSV, schrijft safe_*.csv.")
    }

    Container_Boundary(core, "Core Privacy Logic (privacy_agent.py)") {
        Component(df_processor, "DataFrame Processor", "Pandas", "Voortgangs-loop, roept anonymize_text per rij aan.")
        Component(anonymize_text, "anonymize_text", "Python", "L1: Presidio (in-process). L2: EU-PII-Safeguard (in-process). L3: Ollama (HTTP). Respecteert layers.")
        Component(ollama_client, "Ollama Client", "ollama Python Lib", "Verstuurt JSON-extractie prompt naar LLM.")
    }

    Rel(spa, router_ui, "Haalt webpagina op", "GET /")
    Rel(spa, router_api, "Form-data + SSE", "POST /api/anonymize")
    
    Rel(router_api, file_handler, "Delegeert bestandsopslag")
    Rel(file_handler, fs, "Schrijft/Leest raw_*.csv, safe_*.csv")
    
    Rel(router_api, df_processor, "process_dataframe(df, text_column, config, layers)")
    Rel(df_processor, anonymize_text, "Stuurt text per rij")
    Rel(anonymize_text, ollama_client, "Layer 3", "get_dynamic_prompt + chat")
    
    Rel(ollama_client, llm, "Stuurt prompt", "localhost:11434")
    Rel(llm, ollama_client, "JSON met entiteiten")
```
