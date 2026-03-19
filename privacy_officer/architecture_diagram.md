# 🏗️ Fontys Privacy Officer Agent - Architecture Diagram

Dit diagram toont de stroom van data en communicatie tussen alle componenten van de Privacy Officer applicatie. Alle verwerking vindt **volledig lokaal** plaats — er gaat geen data naar de cloud.

Je kunt de onderstaande Mermaid-code kopiëren en in een tool zoals [Mermaid Live Editor](https://mermaid.live/) of in jullie eigen documentatie plakken.

```mermaid
sequenceDiagram
    autonumber
    actor Gebruiker as Fontys Medewerker
    box DarkBlue Lokale Machine / Server
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
    title Container diagram — Privacy Officer Systeem (volledig lokaal)

    Person(medewerker, "Fontys Medewerker", "Uploadt CSV, kiest lagen en entiteit-types, downloadt resultaat.")

    System_Boundary(c1, "Privacy Officer Agent (lokaal)") {
        Container(spa, "Web Interface", "HTML/CSS/JS", "Upload-formulier, layer-checkboxes, download.")
        Container(api, "Privacy API", "Python, FastAPI", "Verwerkt uploads, orkestreert pipeline, SSE voortgang.")
        Container(agent, "Core Privacy Logic", "Python, Presidio, Transformers", "Triple-layer pipeline: Presidio → EU-PII-Safeguard → Ollama.")
        Container(llm, "Ollama Service", "aya-expanse:8b", "Lokaal LLM voor contextuele PII-extractie.")
        ContainerDb(fs, "Local File System", "Uploads map", "raw_*.csv / safe_*.csv")
    }

    Rel(medewerker, spa, "localhost:8000")
    Rel(spa, api, "Upload / Voortgang / Download")
    Rel(api, fs, "Lezen / Schrijven")
    Rel(api, agent, "process_dataframe()")
    Rel(agent, llm, "localhost:11434")
    Rel(llm, agent, "JSON")
```

---

## 🧩 C4 Component Diagram (Level 3)

Dit is een Niveau 3 (Component) C4-diagram dat inzoomt in de "Privacy API App" en "Core Privacy Logic" containers om te laten zien hoe de Python code intern in elkaar steekt. Dit is nuttig voor developers om te begrijpen hoe applicatie componenten samenwerken.

```mermaid
C4Component
    title Component diagram — Privacy API en Core Logic

    Container(spa, "Web Interface", "HTML/JS", "Upload-formulier en download.")
    Container(fs, "Local File System", "Uploads map", "/uploads/")
    Container(llm, "Ollama Service", "aya-expanse:8b", "Contextuele PII-extractie.")

    Container_Boundary(api, "Privacy API App (app.py)") {
        Component(router_ui, "UI Router", "FastAPI", "Serveert index.html")
        Component(router_api, "API Router", "FastAPI", "Anonymize, voortgang, download")
        Component(file_handler, "File Handler", "File I/O", "Beheert raw/safe CSV")
    }

    Container_Boundary(core, "Core Privacy Logic (privacy_agent.py)") {
        Component(df_processor, "DataFrame Processor", "Pandas", "Verwerkt rijen")
        Component(anonymize_text, "anonymize_text()", "Python", "L1 Presidio · L2 EU-PII · L3 Ollama")
        Component(ollama_client, "Ollama Client", "ollama lib", "Prompt naar lokaal LLM")
    }

    Rel(spa, router_ui, "GET /")
    Rel(spa, router_api, "POST /api/anonymize")
    Rel(router_api, file_handler, "Opslaan")
    Rel(file_handler, fs, "Lezen / Schrijven")
    Rel(router_api, df_processor, "process_dataframe()")
    Rel(df_processor, anonymize_text, "Per rij")
    Rel(anonymize_text, ollama_client, "Layer 3")
    Rel(ollama_client, llm, "localhost:11434")
    Rel(llm, ollama_client, "JSON")
```
