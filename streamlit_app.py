from __future__ import annotations

import io
import json
import os
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

from price_request_parser.classifier import MockClassifier, OpenAIClassifier
from price_request_parser.cleaner import parse_email_file
from price_request_parser.customer_lookup import identify_company, load_customers
from price_request_parser.routing import apply_business_rules, should_fallback


def load_config() -> dict[str, Any]:
    with (PROJECT_ROOT / "config.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def secret_api_key() -> str:
    try:
        return str(st.secrets.get("OPENAI_API_KEY", "")).strip()
    except Exception:
        return ""


def make_uploaded_email(sender: str, subject: str, body: str) -> bytes:
    message = EmailMessage()
    message["From"] = sender.strip() or "unknown@example.invalid"
    message["To"] = "parser@example.invalid"
    message["Subject"] = subject.strip() or "Ohne Betreff"
    message.set_content(body)
    return message.as_bytes()


def parse_bytes(filename: str, data: bytes):
    suffix = Path(filename).suffix.lower()
    if suffix not in {".eml", ".txt"}:
        raise ValueError("Es werden nur .eml- und .txt-Dateien unterstützt.")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(data)
            temporary_path = Path(handle.name)
        return parse_email_file(temporary_path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


def analyse_email(
    *,
    filename: str,
    data: bytes,
    config: dict[str, Any],
    customers: dict[str, str],
    mock: bool,
):
    email = parse_bytes(filename, data)
    email.source_path = filename
    email.customer_company = identify_company(email.sender_domain, customers)

    classifier = MockClassifier() if mock else OpenAIClassifier(
        config.get("pricing_usd_per_million_tokens", {})
    )

    result, usage = classifier.classify(
        email=email,
        model=config["models"]["primary"],
        include_history=False,
        max_chars=int(config.get("max_body_chars_primary", 12000)),
    )
    result.usage.append(usage)

    if should_fallback(result, float(config.get("confidence_threshold", 0.80))):
        fallback_result, fallback_usage = classifier.classify(
            email=email,
            model=config["models"]["fallback"],
            include_history=True,
            max_chars=int(config.get("max_body_chars_fallback", 50000)),
        )
        fallback_result.fallback_used = True
        fallback_result.usage = [*result.usage, fallback_usage]
        result = fallback_result

    result = apply_business_rules(
        result,
        list(config.get("required_shipment_fields", [])),
    )
    total_cost = sum(item.estimated_cost_usd for item in result.usage)

    record = {
        "processed_at_utc": datetime.now(timezone.utc).isoformat(),
        "filename": filename,
        "email": email.to_dict(),
        "result": result.to_dict(),
        "total_estimated_cost_usd": round(total_cost, 10),
    }
    return email, result, record


def build_results_zip(records: list[dict[str, Any]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, record in enumerate(records, start=1):
            original_name = Path(record["filename"]).stem or f"email_{index}"
            safe_name = "".join(
                character if character.isalnum() or character in {"-", "_"} else "_"
                for character in original_name
            )[:80]
            archive.writestr(
                f"{index:03d}_{safe_name}.json",
                json.dumps(record, ensure_ascii=False, indent=2),
            )
    return buffer.getvalue()


st.set_page_config(page_title="Preisanfragen-Parser", page_icon="✉️", layout="wide")
st.title("Preisanfragen aus E-Mails erkennen")
st.caption("Prototyp: Bereinigung, Kundenidentifikation, Klassifikation, Extraktion und Modell-Fallback")

config = load_config()

with st.sidebar:
    st.header("Einstellungen")
    mock_mode = st.toggle("Kostenloser Mock-Test", value=True)
    st.caption("Der Mock-Modus prüft nur die technische Funktion und verwendet keine OpenAI-API.")

    stored_key = secret_api_key()
    entered_key = ""
    if not mock_mode:
        if stored_key:
            st.success("API-Key ist als Streamlit Secret hinterlegt.")
        else:
            entered_key = st.text_input(
                "OpenAI API-Key",
                type="password",
                help="Der Key wird nur für diese Sitzung verwendet und nicht im GitHub-Repository gespeichert.",
            )

    st.divider()
    st.write(f"Primärmodell: `{config['models']['primary']}`")
    st.write(f"Fallback: `{config['models']['fallback']}`")
    st.write("Pflichtfelder:")
    for required_field in config.get("required_shipment_fields", []):
        st.code(required_field, language=None)

    customer_upload = st.file_uploader(
        "Optionale Kundenliste (CSV)",
        type=["csv"],
        help="Spalten: domain,company. Ohne Upload wird customers.csv aus dem Repository verwendet.",
    )

customers_path = PROJECT_ROOT / config["customers_file"]
if customer_upload is not None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as handle:
        handle.write(customer_upload.getvalue())
        uploaded_customer_path = Path(handle.name)
    try:
        customers = load_customers(uploaded_customer_path)
    finally:
        uploaded_customer_path.unlink(missing_ok=True)
else:
    customers = load_customers(customers_path)

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
    include_pasted = st.checkbox("Eingefügten Text zusätzlich analysieren", value=False)
    if include_pasted and body.strip():
        email_items.append(("eingefuegte_email.eml", make_uploaded_email(sender, subject, body)))

st.info(
    "Für echte geschäftliche E-Mails sollte das GitHub-Repository und die Streamlit-App privat bleiben. "
    "Lege den API-Key ausschließlich in den Streamlit Secrets ab, niemals in einer Datei im Repository."
)

analyse_clicked = st.button("E-Mails analysieren", type="primary", disabled=not email_items)

if analyse_clicked:
    api_key = stored_key or entered_key.strip()
    if not mock_mode and not api_key:
        st.error("Für den echten Test fehlt der OpenAI API-Key.")
        st.stop()

    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key

    records: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    progress = st.progress(0, text="Analyse läuft …")

    for index, (filename, data) in enumerate(email_items, start=1):
        try:
            email, result, record = analyse_email(
                filename=filename,
                data=data,
                config=config,
                customers=customers,
                mock=mock_mode,
            )
            records.append(record)
            summary_rows.append(
                {
                    "Datei": filename,
                    "Firma": email.customer_company or "–",
                    "Kategorie": result.category,
                    "Routing": result.route,
                    "Konfidenz": round(result.confidence, 3),
                    "Fallback": "Ja" if result.fallback_used else "Nein",
                    "Transporte": len(result.shipments),
                    "Kosten USD": round(record["total_estimated_cost_usd"], 8),
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
                    "Fallback": "Nein",
                    "Transporte": 0,
                    "Kosten USD": 0,
                }
            )
            st.error(f"Fehler bei {filename}: {exc}")
        progress.progress(index / len(email_items), text=f"{index} von {len(email_items)} verarbeitet")

    progress.empty()

    if summary_rows:
        st.subheader("Ergebnisübersicht")
        st.dataframe(summary_rows, use_container_width=True, hide_index=True)

    for index, record in enumerate(records, start=1):
        result = record["result"]
        with st.expander(
            f"{index}. {record['filename']} — {result['category']} / {result['route']}",
            expanded=index == 1,
        ):
            left, right = st.columns([1, 1])
            with left:
                st.markdown("**Bereinigter Inhalt**")
                st.code(record["email"]["current_body"] or "(leer)", language=None)
                if record["email"].get("quoted_history"):
                    st.markdown("**Abgetrennter Verlauf**")
                    st.code(record["email"]["quoted_history"], language=None)
            with right:
                st.markdown("**Extrahierte Transporte**")
                if result["shipments"]:
                    st.dataframe(result["shipments"], use_container_width=True, hide_index=True)
                else:
                    st.write("Keine Transporte extrahiert.")
                if result["missing_fields"]:
                    st.warning("Fehlende Pflichtfelder: " + ", ".join(result["missing_fields"]))
                if result["ambiguities"]:
                    st.warning("Unklarheiten: " + ", ".join(result["ambiguities"]))

            st.download_button(
                "JSON-Ergebnis herunterladen",
                data=json.dumps(record, ensure_ascii=False, indent=2),
                file_name=f"{Path(record['filename']).stem}_ergebnis.json",
                mime="application/json",
                key=f"download_{index}_{record['filename']}",
            )

    if records:
        st.download_button(
            "Alle JSON-Ergebnisse als ZIP herunterladen",
            data=build_results_zip(records),
            file_name="preisanfragen_ergebnisse.zip",
            mime="application/zip",
        )
