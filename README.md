# Preisanfragen-Parser 2.0

Browser-Prototyp zur regelbasierten Erkennung und Extraktion von Transport-Preisanfragen.

## Eigenschaften

- keine OpenAI-API
- kein API-Key
- keine Tokenkosten
- Upload von `.eml` und `.txt`
- Signatur- und Verlaufstrennung
- Kundenidentifikation über Domain
- transparente Klassifikationsregeln
- JSON- und ZIP-Export

## Deployment auf Streamlit Community Cloud

1. Alle Dateien dieses Ordners in das GitHub-Repository hochladen.
2. In Streamlit als Main file `streamlit_app.py` auswählen.
3. Python-Version `3.12` einstellen.
4. Deploy/Reboot ausführen.

Es werden keine Secrets benötigt.

## Kundenliste

`customers.csv`:

```csv
domain,company
kunde.de,Musterkunde GmbH
```

## Wichtig

Version 2.0 ist ein technischer und fachlicher Regel-Prototyp. Die Regeln können anhand echter E-Mails erweitert werden. Sie ersetzt noch keine produktive Qualitätssicherung.
