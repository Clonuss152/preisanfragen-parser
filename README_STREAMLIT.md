# Preisanfragen-Parser als Streamlit-App

## Online bereitstellen

1. Auf GitHub ein **privates** Repository erstellen.
2. Den vollständigen Inhalt dieses Ordners in das Repository hochladen. `streamlit_app.py` muss im Hauptverzeichnis liegen.
3. Bei Streamlit Community Cloud mit GitHub anmelden.
4. Neue App erstellen und auswählen:
   - Repository: dein privates Repository
   - Branch: `main`
   - Main file path: `streamlit_app.py`
5. Unter **Advanced settings → Secrets** eintragen:

```toml
OPENAI_API_KEY = "sk-..."
```

6. Deploy starten.

## Test

- App öffnen.
- `Kostenloser Mock-Test` zunächst aktiviert lassen.
- Eine `.eml`-Datei hochladen oder E-Mail-Text einfügen.
- `E-Mails analysieren` anklicken.
- Danach Mock-Modus ausschalten, um die echte OpenAI-Auswertung zu testen.

## Sicherheit

- API-Key niemals in GitHub hochladen.
- Keine echten E-Mails im Repository speichern.
- Für geschäftliche Daten Repository und App privat halten.
- `customers.csv` kann im privaten Repository gepflegt oder bei jedem Test über die Oberfläche hochgeladen werden.
