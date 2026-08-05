# Preisanfragen-Parser 2.1

Kostenloser, regelbasierter Streamlit-Prototyp ohne API und ohne externe KI-Verarbeitung.

## Neuerungen in 2.1

- deutsche und englische Preisanfragen
- typische Formulierungen wie `RFQ`, `request for quotation`, `please quote`, `best rate`
- gewichtetes Scoring statt einfacher Ja/Nein-Suche
- Gegenregeln gegen Fehlklassifikationen, z. B. `price remains unchanged`
- verständliche Ergebnisansicht mit deutschen Bezeichnungen
- technische Details und JSON bleiben verfügbar
- englische Beispielmail unter `samples/price_request_english.eml`

## Deployment

- Main file: `streamlit_app.py`
- Python: 3.12
- keine Secrets erforderlich
- Abhängigkeit: `streamlit==1.45.1`

## Unterstützte Dateien

- `.eml`
- `.txt`
