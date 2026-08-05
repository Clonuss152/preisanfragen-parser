from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from .cleaner import parse_email_file
from .customer_lookup import identify_company
from .rule_engine import classify


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
        if temporary_path:
            temporary_path.unlink(missing_ok=True)


def analyse(filename: str, data: bytes, config: dict[str, Any], customers: dict[str, str]):
    email = parse_bytes(filename, data)
    email.source_path = filename
    email.customer_company = identify_company(email.sender_domain, customers)
    result = classify(
        email,
        required_fields=list(config.get("required_shipment_fields", [])),
        thresholds=dict(config.get("classification_thresholds", {})),
    )
    return email, result
