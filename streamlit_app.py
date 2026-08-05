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


st.set_page_config(page_title="Preisanfragen-Parser 2.2", page_icon="✉️", layout="wide")
st.title("Preisanfragen-Parser 2.2")
st.caption("Rein regelbasierter Prototyp – keine API, keine Tokenkosten, keine externe KI-Verarbeitung")

config = load_config()

with st.sidebar:
    st.header("Konfiguration")
    st.success("Kostenfreier Offline-Modus")
    st.write("Analyse-Engine: `rule-based-v2.1-de-en`")
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

with st.expander("Was kann Version 2.1?", expanded=False):
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
        category_labels = {
            "PRICE_REQUEST": "Preisanfrage",
            "BOOKING": "Buchung / Beauftragung",
            "STATUS_UPDATE": "Statusmeldung",
            "OTHER": "Keine Preisanfrage",
            "UNCLEAR": "Manuelle Prüfung",
        }
        route_labels = {
            "complete": "Vollständig",
            "incomplete": "Unvollständig",
            "not_request": "Keine Preisanfrage",
            "review": "Manuelle Prüfung",
        }
        field_labels = {
            "pickup_location": "Abholort",
            "pickup_date": "Abholdatum",
            "delivery_location": "Zustellort",
            "delivery_date": "Zustelldatum",
            "goods": "Ware",
            "pallets": "Paletten",
            "weight_kg": "Gewicht",
            "loading_meters": "Lademeter",
            "vehicle_type": "Fahrzeug",
            "temperature_min_c": "Temperatur min.",
            "temperature_max_c": "Temperatur max.",
            "adr": "ADR",
        }

        def display_value(key: str, value: Any) -> str:
            if value is None or value == "":
                return "–"
            if key == "weight_kg":
                return f"{float(value):,.0f} kg".replace(",", ".")
            if key == "loading_meters":
                return f"{value} Ldm"
            if key in {"temperature_min_c", "temperature_max_c"}:
                return f"{value} °C"
            if key == "adr":
                return "Ja" if value else "Nein"
            if key in {"pickup_date", "delivery_date"}:
                try:
                    return datetime.fromisoformat(str(value)).strftime("%d.%m.%Y")
                except ValueError:
                    return str(value)
            return str(value)

        for record in records:
            result = record["result"]
            email = record["email"]
            title = f"{record['filename']} – {category_labels.get(result['category'], result['category'])} / {route_labels.get(result['route'], result['route'])}"
            with st.expander(title, expanded=True):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Kategorie", category_labels.get(result["category"], result["category"]))
                c2.metric("Status", route_labels.get(result["route"], result["route"]))
                c3.metric("Konfidenz", f"{result['confidence'] * 100:.0f} %")
                c4.metric("Kosten", "0,00 €")

                st.markdown("### E-Mail")
                mail_col1, mail_col2 = st.columns(2)
                mail_col1.write(f"**Auftraggeber:** {email.get('customer_company') or 'Nicht erkannt'}")
                mail_col1.write(f"**Absender:** {email.get('sender_email') or '–'}")
                mail_col2.write(f"**Betreff:** {email.get('subject') or '–'}")
                mail_col2.write(f"**Anhänge:** {', '.join(email.get('attachment_names', [])) or 'Keine'}")

                if result["missing_fields"]:
                    readable_missing = [field_labels.get(item, item) for item in result["missing_fields"]]
                    st.error("Fehlende Pflichtfelder: " + ", ".join(readable_missing))
                elif result["category"] == "PRICE_REQUEST":
                    st.success("Alle definierten Pflichtfelder sind vorhanden.")

                st.markdown("### Transportdaten")
                if result["shipments"]:
                    for shipment_index, shipment in enumerate(result["shipments"], start=1):
                        st.markdown(f"**Transport {shipment_index}**")
                        left, right = st.columns(2)
                        left.markdown("**Abholung**")
                        left.write(display_value("pickup_location", shipment.get("pickup_location")))
                        left.write(display_value("pickup_date", shipment.get("pickup_date")))
                        right.markdown("**Zustellung**")
                        right.write(display_value("delivery_location", shipment.get("delivery_location")))
                        right.write(display_value("delivery_date", shipment.get("delivery_date")))

                        details = []
                        for key in ["goods", "pallets", "weight_kg", "loading_meters", "vehicle_type", "temperature_min_c", "temperature_max_c", "adr"]:
                            details.append({"Feld": field_labels[key], "Wert": display_value(key, shipment.get(key))})
                        st.dataframe(details, use_container_width=True, hide_index=True)
                else:
                    st.info("Keine Transportdaten extrahiert.")

                st.markdown("### Prüfansichten")
                tab_labels = ["Bereinigter E-Mail-Text", "Bewertung", "Technische Details / JSON"]
                if email.get("quoted_history"):
                    tab_labels.insert(1, "Abgetrennter Mailverlauf")
                tabs = st.tabs(tab_labels)

                tab_index = 0
                with tabs[tab_index]:
                    st.code(email.get("current_body") or "", language=None)
                tab_index += 1

                if email.get("quoted_history"):
                    with tabs[tab_index]:
                        st.code(email["quoted_history"], language=None)
                    tab_index += 1

                with tabs[tab_index]:
                    st.write("**Ausgelöste Regeln:**")
                    st.write(result["matched_rules"] or ["Keine Regel ausgelöst"])
                    st.write("**Punktestände:**", result["scores"])
                    st.caption(f"Engine: {result.get('engine', 'rule-based')}")
                    if result["ambiguities"]:
                        st.warning(" | ".join(result["ambiguities"]))
                tab_index += 1

                with tabs[tab_index]:
                    st.json(record)

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
