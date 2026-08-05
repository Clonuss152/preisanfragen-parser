from __future__ import annotations

import io
import json
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from price_request_parser.customer_lookup import load_customers
from price_request_parser.service import analyse


def load_config() -> dict[str, Any]:
    with (PROJECT_ROOT / "config.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def make_uploaded_email(sender: str, subject: str, body: str) -> bytes:
    message = EmailMessage()
    message["From"] = sender.strip() or "unknown@example.invalid"
    message["To"] = "parser@example.invalid"
    message["Subject"] = subject.strip() or "Ohne Betreff"
    message.set_content(body)
    return message.as_bytes()


def safe_name(value: str) -> str:
    stem = Path(value).stem or "email"
    return "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in stem)[:80]


def build_results_zip(records: list[dict[str, Any]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, record in enumerate(records, start=1):
            base = safe_name(record["filename"])
            archive.writestr(
                f"{index:03d}_{base}.json",
                json.dumps(record, ensure_ascii=False, indent=2),
            )
            cleaned = record["email"]["current_body"]
            archive.writestr(f"{index:03d}_{base}_bereinigt.txt", cleaned)
    return buffer.getvalue()


st.set_page_config(page_title="Preisanfragen-Parser 2.0", page_icon="✉️", layout="wide")
st.title("Preisanfragen-Parser 2.0")
st.caption("Rein regelbasierter Prototyp – keine API, keine Tokenkosten, keine externe KI-Verarbeitung")

config = load_config()

with st.sidebar:
    st.header("Konfiguration")
    st.success("Kostenfreier Offline-Modus")
    st.write("Analyse-Engine: `rule-based-v2`")
    st.write("Pflichtfelder:")
    for field in config.get("required_shipment_fields", []):
        st.code(field, language=None)
    st.divider()
    st.caption(
        "Die Klassifikation basiert auf sichtbaren Schlüsselwörtern und Extraktionsregeln. "
        "Sie ist transparent, aber weniger flexibel als ein Sprachmodell."
    )
    customer_upload = st.file_uploader(
        "Optionale Kundenliste (CSV)",
        type=["csv"],
        help="Spalten: domain,company",
    )

if customer_upload is not None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as handle:
        handle.write(customer_upload.getvalue())
        customer_path = Path(handle.name)
    try:
        customers = load_customers(customer_path)
    finally:
        customer_path.unlink(missing_ok=True)
else:
    customers = load_customers(PROJECT_ROOT / config["customers_file"])

with st.expander("Was kann Version 2.0?", expanded=False):
    st.markdown(
        """
- `.eml`- und `.txt`-Dateien einlesen
- HTML in Text umwandeln
- Signaturen, Disclaimer und alte Mailverläufe abtrennen
- Auftraggeber über Absenderdomain und Kundenliste bestimmen
- Preisanfrage, Buchung, Statusmeldung, Sonstiges oder unklar unterscheiden
- Relation, Termine, Gewicht, Paletten, Lademeter, Temperatur und ADR regelbasiert extrahieren
- Routing nach `complete`, `incomplete`, `not_request` oder `review`
- Ergebnisse als JSON und ZIP herunterladen
        """
    )

upload_tab, paste_tab = st.tabs(["E-Mail-Dateien hochladen", "E-Mail einfügen"])
email_items: list[tuple[str, bytes]] = []

with upload_tab:
    uploaded_files = st.file_uploader(
        "Eine oder mehrere .eml- oder .txt-Dateien auswählen",
        type=["eml", "txt"],
        accept_multiple_files=True,
    )
    if uploaded_files:
        email_items.extend((item.name, item.getvalue()) for item in uploaded_files)

with paste_tab:
    col1, col2 = st.columns(2)
    sender = col1.text_input("Absender", placeholder="max.mustermann@kunde.de")
    subject = col2.text_input("Betreff", placeholder="Preisanfrage München – Paris")
    body = st.text_area("E-Mail-Text", height=260)
    include_pasted = st.checkbox("Eingefügten Text analysieren", value=False)
    if include_pasted and body.strip():
        email_items.append(("eingefuegte_email.eml", make_uploaded_email(sender, subject, body)))

analyse_clicked = st.button("E-Mails analysieren", type="primary", disabled=not email_items)

if analyse_clicked:
    records: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    progress = st.progress(0, text="Analyse läuft …")

    for index, (filename, data) in enumerate(email_items, start=1):
        try:
            email, result = analyse(filename, data, config, customers)
            record = {
                "processed_at_utc": datetime.now(timezone.utc).isoformat(),
                "filename": filename,
                "email": email.to_dict(),
                "result": result.to_dict(),
                "cost": {"currency": "EUR", "amount": 0.0},
            }
            records.append(record)
            summary_rows.append(
                {
                    "Datei": filename,
                    "Firma": email.customer_company or "–",
                    "Kategorie": result.category,
                    "Routing": result.route,
                    "Konfidenz": result.confidence,
                    "Transporte": len(result.shipments),
                    "Fehlende Pflichtfelder": ", ".join(result.missing_fields) or "–",
                }
            )
        except Exception as exc:
            summary_rows.append(
                {
                    "Datei": filename,
                    "Firma": "–",
                    "Kategorie": "ERROR",
                    "Routing": "error",
                    "Konfidenz": 0,
                    "Transporte": 0,
                    "Fehlende Pflichtfelder": str(exc),
                }
            )
        progress.progress(index / len(email_items), text=f"{index} von {len(email_items)} verarbeitet")

    progress.empty()
    st.subheader("Übersicht")
    st.dataframe(summary_rows, use_container_width=True, hide_index=True)

    if records:
        st.download_button(
            "Alle Ergebnisse als ZIP herunterladen",
            data=build_results_zip(records),
            file_name="preisanfragen_ergebnisse.zip",
            mime="application/zip",
        )

        st.subheader("Detailergebnisse")
        for record in records:
            result = record["result"]
            email = record["email"]
            with st.expander(f"{record['filename']} – {result['category']} / {result['route']}"):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Kategorie", result["category"])
                c2.metric("Routing", result["route"])
                c3.metric("Konfidenz", result["confidence"])
                c4.metric("Kosten", "0,00 €")

                st.markdown("**Erkannter Auftraggeber**")
                st.write(email.get("customer_company") or "Nicht über Kundenliste erkannt")

                st.markdown("**Bereinigter E-Mail-Text**")
                st.code(email.get("current_body") or "", language=None)

                if email.get("quoted_history"):
                    with st.expander("Abgetrennter Mailverlauf"):
                        st.code(email["quoted_history"], language=None)

                st.markdown("**Extrahierte Transportdaten**")
                if result["shipments"]:
                    st.json(result["shipments"])
                else:
                    st.info("Keine Transportdaten extrahiert.")

                st.markdown("**Ausgelöste Regeln**")
                st.write(result["matched_rules"] or ["Keine Regel ausgelöst"])
                st.write("Punktestände:", result["scores"])

                if result["ambiguities"]:
                    st.warning(" | ".join(result["ambiguities"]))

                st.download_button(
                    "JSON herunterladen",
                    data=json.dumps(record, ensure_ascii=False, indent=2),
                    file_name=f"{safe_name(record['filename'])}.json",
                    mime="application/json",
                    key=f"download_{safe_name(record['filename'])}_{len(record['filename'])}",
                )

st.divider()
st.caption(
    "Hinweis: Diese Version sendet keine E-Mail-Inhalte an OpenAI oder andere KI-Dienste. "
    "Die Verarbeitung findet ausschließlich innerhalb der laufenden Streamlit-App statt."
)
