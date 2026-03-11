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
        participant Ollama as Ollama Service (Llama 3.2 Engine)
    end
    
    note over Gebruiker, Ollama: Volledig offline, geen cloud of internet verbinding

    Gebruiker->>UI: Uploadt raw CSV bestand (bijv. fontys_nse.csv)
    Gebruiker->>UI: Vul kolomnaam in (bijv. 'OpenReactie')
    UI->>API: HTTP POST /api/anonymize (Multipart Form Data)
    
    activate API
    API->>API: Slaat .csv lokaal op in /uploads/raw_*.csv
    API->>Core: process_dataframe(df, kolom='OpenReactie')
    
    activate Core
    loop Elke zin in de gekozen kolom
        Core->>Ollama: HTTP POST /api/chat (Systeemprompt + Zin)
        activate Ollama
        note right of Ollama: Leest zin, zoekt PII <br>en past [TAGS] toe
        Ollama-->>Core: Retourneert geanonimiseerde tekst
        deactivate Ollama
        
        Core->>Core: Valideert output (Lengte check & Leeg check)
    end
    
    Core-->>API: Retourneert nieuwe, veilige Pandas DataFrame
    deactivate Core
    
    API->>API: Slaat veilige DataFrame op als /uploads/safe_*.csv
    API-->>UI: JSON { success: true, download_url: /api/... }
    deactivate API
    
    UI-->>Gebruiker: Toont succesmelding en download link
    Gebruiker->>UI: Klikt "Download"
    UI->>API: HTTP GET /api/download/safe_*.csv
    API-->>Gebruiker: Veilige CSV File
```

### 🧩 Componenten Uitleg:
1. **Web Interface (HTML/JS)**: De gebruiksvriendelijke "voorkant" die in de browser van de gebruiker draait (maar wel lokaal gehost wordt).
2. **FastAPI Backend ([app.py](file:///c:/fontys/semester_4/group/agents/src/api/app.py))**: De beveiliger en logistiek manager. Het ontvangt het bestand, roept de Python logica aan, en regelt de downloads.
3. **Privacy Agent ([privacy_agent.py](file:///c:/fontys/semester_4/group/agents/privacy_agent.py))**: De "hersenen" van ons Python script. Hier zit de strenge System Prompt en de beveiliging in gebouwd (het checken op fouten).
4. **Ollama Service**: De daadwerkelijke AI (Llama 3.2). Luistert lokaal op poort `11434` en voert het zware taalbegrip uit. Omdat het **niet** in de cloud draait, lekt er geen data.


---

## 🏛️ C4 Container Diagram

Dit is een Niveau 2 (Container) C4-diagram dat perfect aantoont hoe de systemen van elkaar geïsoleerd zijn. De grijze rand ("System_Boundary") maakt direct duidelijk dat de hele oplossing binnen de beveiligde IT-infrastructuur van Fontys kan draaien.

```mermaid
C4Container
    title Container diagram voor het Fontys Privacy Officer Systeem

    Person(medewerker, "Fontys Kwaliteitsmedewerker", "Uploadt NSE data en downloadt geanonimiseerde resultaten.")

    System_Boundary(c1, "Privacy Officer Agent (Lokale Omgeving)") {
        Container(spa, "Web Interface", "HTML, CSS, JavaScript", "Biedt de gebruikersinterface voor de medewerker om bestanden te uploaden.")
        Container(api, "Privacy API App", "Python, FastAPI", "Verwerkt bestandsuploads, orkestreert het proces via Pandas, en garandeert veilige I/O operaties lokaal.")
        Container(agent, "Core Privacy Logic", "Python, Pandas", "Leest het CSV bestand regel voor regel en communiceert met het lokale LLM cluster.")
        Container(llm, "Ollama Service", "Ollama (Llama 3.2)", "Het lokaal draaiende AI taalmodel dat offline entiteiten herkent en maskeert via de System Prompt.")
        
        ContainerDb(fs, "Local File System", "Uploads Map", "Slaat tijdelijk de ruwe en geanonimiseerde CSV bestanden op de host-machine op.")
    }

    Rel(medewerker, spa, "Bezoekt", "Webbrowser (http://localhost:8000)")
    Rel(spa, api, "Maakt API calls", "JSON/HTTP POST")
    Rel(api, fs, "Slaat op / Leest", "Lokale Bestands-I/O")
    Rel(api, agent, "Roept aan", "Interne Functie (process_dataframe)")
    Rel(agent, llm, "Vraagt anonimisering aan", "HTTP POST (localhost:11434)")
    Rel(llm, agent, "Retourneert string data", "JSON")
```

---

## 🧩 C4 Component Diagram (Level 3)

Dit is een Niveau 3 (Component) C4-diagram dat inzoomt in de "Privacy API App" en "Core Privacy Logic" containers om te laten zien hoe de Python code intern in elkaar steekt. Dit is nuttig voor developers om te begrijpen hoe applicatie componenten samenwerken.

```mermaid
C4Component
    title Component diagram voor de Privacy Officer API en Core Logic

    Container(spa, "Web Interface", "HTML/JS", "Biedt de gebruikersinterface.")
    Container(fs, "Local File System", "Uploads Map", "/uploads/")
    Container(llm, "Ollama Service", "Ollama", "Lokaal AI model")

    Container_Boundary(api, "Privacy API App (app.py)") {
        Component(router_ui, "UI Router", "FastAPI Route", "Serveert index.html op '/'")
        Component(router_api, "API Router", "FastAPI Route", "Ontvangt uploads op '/api/anonymize' en regelt downloads op '/api/download'")
        Component(file_handler, "File Handler", "Python File I/O", "Slaat uploads op en leest CSV data.")
    }

    Container_Boundary(core, "Core Privacy Logic (privacy_agent.py)") {
        Component(df_processor, "DataFrame Processor", "Pandas", "Beheert in-memory dataraster en the voortgangs-loop (progress bar).")
        Component(anonymizer, "Text Anonymizer", "Python Functie", "Past beveiligingschecks en LLM prompt toe per tekst-alinea.")
        Component(ollama_client, "Ollama Client", "Ollama Python Lib", "Verstuurt HTTP integratie aanroepen naar backend LLM.")
    }

    Rel(spa, router_ui, "Haalt webpagina op", "GET /")
    Rel(spa, router_api, "Stuurt form-data CSV & vraagt download", "POST /api/anonymize", "GET /api/download")
    
    Rel(router_api, file_handler, "Delegeert bestandsopslag")
    Rel(file_handler, fs, "Schrijft/Leest raw_*.csv bestanden")
    
    Rel(router_api, df_processor, "Roept process_dataframe() aan met filepath")
    Rel(df_processor, anonymizer, "Stuurt text per DataFrame rij")
    Rel(anonymizer, ollama_client, "Parse text en voegt SYSTEM PROMPT toe")
    
    Rel(ollama_client, llm, "Stuurt prompt", "Local API (11434)")
    Rel(llm, ollama_client, "Geeft schone text terug")
    
    Rel(df_processor, fs, "Slaat veilige dataframe op als safe_*.csv")
```
