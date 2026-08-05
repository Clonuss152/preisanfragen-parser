from __future__ import annotations

from typing import Any

from .models import ParseResult


PRICE_CATEGORIES = {"PRICE_REQUEST"}


def _missing_required(shipments: list[dict[str, Any]], required_fields: list[str]) -> list[str]:
    missing: list[str] = []
    if not shipments:
        return ["shipments"]
    for index, shipment in enumerate(shipments):
        for field in required_fields:
            value = shipment.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(f"shipments[{index}].{field}")
    return missing


def apply_business_rules(result: ParseResult, required_fields: list[str]) -> ParseResult:
    if result.category not in PRICE_CATEGORIES:
        result.route = "review" if result.category == "UNCLEAR" else "not_request"
        return result

    if result.attachment_relevant:
        result.route = "review"
        return result

    rule_missing = _missing_required(result.shipments, required_fields)
    merged = list(dict.fromkeys([*result.missing_fields, *rule_missing]))
    result.missing_fields = merged
    result.route = "complete" if not rule_missing else "incomplete"
    return result


def should_fallback(result: ParseResult, confidence_threshold: float) -> bool:
    return (
        result.needs_fallback
        or result.category == "UNCLEAR"
        or result.confidence < confidence_threshold
    )
