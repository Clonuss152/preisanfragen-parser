# Prototyp: Preisanfragen aus E-Mails erkennen

Der Prototyp verarbeitet lokale `.eml`- und `.txt`-Dateien, bereinigt den aktuellen Nachrichtentext regelbasiert, identifiziert den Auftraggeber über die Absenderdomain, klassifiziert und extrahiert mit einem kleinen OpenAI-Modell und verwendet nur bei Unsicherheit ein Fallback-Modell.

## Ergebnisordner

- `output/complete`: Preisanfrage und alle konfigurierten Pflichtfelder vorhanden
- `output/incomplete`: klare Preisanfrage, Pflichtfelder fehlen
- `output/not_request`: keine Preisanfrage
- `output/review`: unklar oder relevante Angaben nur im Anhang
- `output/error`: technische Fehler

Zu jeder Mail werden die Originaldatei, das strukturierte JSON-Ergebnis und optional der bereinigte Text abgelegt.

## Datenschutz

Der API-Aufruf setzt `store=False`. An die API gehen nur Absenderadresse, erkannte Firma, Betreff, bereinigter Nachrichtentext und Anhangsnamen. Die Originaldatei wird nicht hochgeladen. Bitte vor einem Produktivbetrieb trotzdem Datenschutz, Auftragsverarbeitung, Datenresidenz und interne Freigaben prüfen.

## Installation unter Windows

```powershell
cd preisanfragen_prototyp
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:OPENAI_API_KEY="sk-..."
python run.py
```

Ohne API-Key kann die technische Verarbeitung lokal getestet werden:

```powershell
python run.py --mock
```

Einzelne Datei verarbeiten:

```powershell
python run.py --mock samples\preisanfrage.eml
python run.py C:\Pfad\zu\einer_mail.eml
```

## Konfiguration

In `config.json` können Modelle, Konfidenzschwelle, Pflichtfelder, Zeichenlimits, Routingverhalten und Preise angepasst werden.

Standardmäßig:

- Primärmodell: `gpt-5-nano`
- Fallback: `gpt-5-mini`
- Fallback nur bei Unsicherheit oder niedriger Konfidenz
- Keine Eskalation allein wegen fehlender Felder
- Pflichtfelder: Abholort, Zustellort und Abholdatum

Die Preise in der Konfiguration dienen nur der Kostenschätzung und müssen bei Preisänderungen aktualisiert werden.

## Kundenstamm

`customers.csv`:

```csv
domain,company
kunde.de,Musterkunde GmbH
```

Damit wird die Firma ohne Modellaufruf über die Absenderdomain bestimmt.

## Outlook / Microsoft 365

Dieser MVP liest exportierte `.eml`-Dateien. Für den Produktivbetrieb sollte der gleiche Kern über Microsoft Graph, Power Automate oder einen überwachten Exchange-Posteingang aufgerufen werden. Outlook-`.msg` wird in dieser ersten Version nicht verarbeitet.

## Wichtige Grenze des MVP

Anhänge werden nur anhand ihres Dateinamens erkannt, aber noch nicht inhaltlich ausgelesen. Meldet das Modell, dass die wesentlichen Angaben nur im Anhang stehen, landet die Mail in `review`.
