from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from price_request_parser.cleaner import parse_email_file
from price_request_parser.routing import apply_business_rules
from price_request_parser.models import ParseResult


def test_signature_and_history_are_removed(tmp_path: Path) -> None:
    path = tmp_path / "mail.eml"
    path.write_text(
        "From: Max <max@kunde.de>\n"
        "Subject: Preisanfrage\n"
        "Content-Type: text/plain; charset=utf-8\n\n"
        "Bitte Preis für 82343 Pöcking nach 20095 Hamburg.\n\n"
        "Mit freundlichen Grüßen\nMax\n\n"
        "-----Original Message-----\nOld text",
        encoding="utf-8",
    )
    email = parse_email_file(path)
    assert "Mit freundlichen" not in email.current_body
    assert "Old text" in email.quoted_history
    assert email.sender_domain == "kunde.de"


def test_business_completeness() -> None:
    result = ParseResult(
        category="PRICE_REQUEST",
        confidence=0.99,
        needs_fallback=False,
        attachment_relevant=False,
        shipments=[{
            "pickup_location": "82343 Pöcking",
            "delivery_location": "20095 Hamburg",
            "pickup_date": "2026-08-07",
        }],
        missing_fields=[],
        ambiguities=[],
        model_used="test",
    )
    apply_business_rules(result, ["pickup_location", "delivery_location", "pickup_date"])
    assert result.route == "complete"
