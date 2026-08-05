from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .models import EmailData, ParseResult


PRICE_RULES: list[tuple[str, re.Pattern[str], int]] = [
    ("preis_anfrage", re.compile(r"\b(?:preis|rate|frachtpreis|angebot|offerte|quotation|quote)\b", re.I), 3),
    ("preis_bitte", re.compile(r"\b(?:bitte|please).{0,40}\b(?:preis|rate|angebot|quote)\b", re.I | re.S), 3),
    ("kosten_frage", re.compile(r"\b(?:was kostet|zu welchem preis|best price|your rate|can you quote)\b", re.I), 4),
    ("verfuegbarkeit_preis", re.compile(r"\b(?:preis und verfügbarkeit|rate and availability|capacity and price)\b", re.I), 4),
]

BOOKING_RULES: list[tuple[str, re.Pattern[str], int]] = [
    ("beauftragung", re.compile(r"\b(?:hiermit beauftragen|wir beauftragen|transportauftrag|booking confirmation|we hereby book)\b", re.I), 4),
    ("fix_buchen", re.compile(r"\b(?:bitte fest buchen|please book|auftrag ist fix|transport is confirmed)\b", re.I), 4),
]

STATUS_RULES: list[tuple[str, re.Pattern[str], int]] = [
    ("status", re.compile(r"\b(?:status|eta|verspätung|delay|abgeladen|beladen|delivered|loaded|entladen)\b", re.I), 2),
    ("status_frage", re.compile(r"\b(?:wo ist der lkw|aktueller stand|current status|please advise eta)\b", re.I), 4),
]

ATTACHMENT_HINT = re.compile(r"\b(?:siehe anhang|see attachment|details im anhang|attached request|anbei die anfrage)\b", re.I)
ROUTE_HINT = re.compile(r"\b(?:von|abholung|pickup|loading|ladeort)\b.{0,100}\b(?:nach|zustellung|delivery|unloading|entladeort)\b", re.I | re.S)

DATE_PATTERN = re.compile(r"\b(\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?)\b")
ISO_DATE_PATTERN = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
POSTCODE_CITY_PATTERN = re.compile(r"\b(?:(?P<country>[A-Z]{2})[- ]?)?(?P<postcode>\d{4,5})\s+(?P<city>[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\- ]{2,40})")
WEIGHT_PATTERN = re.compile(r"\b(\d{1,3}(?:[.,]\d{3})*|\d+(?:[.,]\d+)?)\s*(kg|t|to|tonnen|tons?)\b", re.I)
PALLET_PATTERN = re.compile(r"\b(\d{1,3})\s*(?:euro[- ]?)?(?:paletten|pallets?|pl)\b", re.I)
LDM_PATTERN = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(?:ldm|lademeter)\b", re.I)
TEMPERATURE_PATTERN = re.compile(r"(?<!\d)(-?\d{1,2}(?:[.,]\d+)?)\s*(?:°\s*)?c\b", re.I)

LABEL_PATTERNS: dict[str, re.Pattern[str]] = {
    "pickup_location": re.compile(r"(?im)^\s*(?:abholung|ladeort|pickup|loading)\s*[:\-]\s*(.+)$"),
    "delivery_location": re.compile(r"(?im)^\s*(?:zustellung|entladeort|delivery|unloading)\s*[:\-]\s*(.+)$"),
    "pickup_date": re.compile(r"(?im)^\s*(?:abholdatum|ladedatum|pickup date|loading date)\s*[:\-]\s*(.+)$"),
    "delivery_date": re.compile(r"(?im)^\s*(?:zustelldatum|entladedatum|delivery date|unloading date)\s*[:\-]\s*(.+)$"),
    "goods": re.compile(r"(?im)^\s*(?:ware|goods|commodity)\s*[:\-]\s*(.+)$"),
    "vehicle_type": re.compile(r"(?im)^\s*(?:fahrzeug|vehicle|equipment|truck)\s*[:\-]\s*(.+)$"),
}


def _score(text: str, rules: list[tuple[str, re.Pattern[str], int]]) -> tuple[int, list[str]]:
    total = 0
    matches: list[str] = []
    for name, pattern, points in rules:
        if pattern.search(text):
            total += points
            matches.append(f"{name} (+{points})")
    return total, matches


def _clean_location(value: str) -> str:
    value = re.split(r"\s{2,}|;|\|", value.strip())[0]
    # Common format: "10.08.2026 in 80331 München". Keep only the location part.
    value = re.sub(r"^\s*(?:20\d{2}-\d{2}-\d{2}|\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?)\s+(?:in|at)\s+", "", value, flags=re.I)
    value = re.sub(r"\b(?:am|on)\s+\d{1,2}[./-]\d{1,2}.*$", "", value, flags=re.I).strip(" ,.-")
    return value[:100]


def _normalize_date(value: str) -> str:
    value = value.strip().split()[0].strip(" ,;.")
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", value):
        return value
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return value


def _label_value(text: str, key: str) -> str | None:
    match = LABEL_PATTERNS[key].search(text)
    return match.group(1).strip() if match else None


def _extract_locations(text: str) -> tuple[str | None, str | None]:
    pickup = _label_value(text, "pickup_location")
    delivery = _label_value(text, "delivery_location")

    if pickup and delivery:
        return _clean_location(pickup), _clean_location(delivery)

    route = re.search(
        r"\b(?:von|from)\s+(.{2,80}?)\s+(?:nach|to)\s+(.{2,80}?)(?:[\n,.;]|$)",
        text,
        re.I,
    )
    if route:
        return pickup or _clean_location(route.group(1)), delivery or _clean_location(route.group(2))

    found = [f"{m.group('country') + '-' if m.group('country') else ''}{m.group('postcode')} {m.group('city').strip()}" for m in POSTCODE_CITY_PATTERN.finditer(text)]
    if len(found) >= 2:
        return pickup or found[0], delivery or found[1]
    return _clean_location(pickup) if pickup else None, _clean_location(delivery) if delivery else None


def _extract_dates(text: str) -> tuple[str | None, str | None]:
    pickup = _label_value(text, "pickup_date")
    delivery = _label_value(text, "delivery_date")
    pickup_date = _normalize_date(pickup) if pickup else None
    delivery_date = _normalize_date(delivery) if delivery else None

    all_dates = ISO_DATE_PATTERN.findall(text) + DATE_PATTERN.findall(text)
    normalized: list[str] = []
    for value in all_dates:
        item = _normalize_date(value)
        if item not in normalized:
            normalized.append(item)
    if pickup_date is None and normalized:
        pickup_date = normalized[0]
    if delivery_date is None and len(normalized) > 1:
        delivery_date = normalized[1]
    return pickup_date, delivery_date


def _number(value: str) -> float:
    value = value.replace(".", "").replace(",", ".")
    return float(value)


def extract_shipment(text: str) -> dict[str, Any]:
    pickup_location, delivery_location = _extract_locations(text)
    pickup_date, delivery_date = _extract_dates(text)

    weight_kg: float | None = None
    weight_match = WEIGHT_PATTERN.search(text)
    if weight_match:
        weight_kg = _number(weight_match.group(1))
        if weight_match.group(2).lower() in {"t", "to", "tonnen", "ton", "tons"}:
            weight_kg *= 1000

    pallets_match = PALLET_PATTERN.search(text)
    ldm_match = LDM_PATTERN.search(text)
    temperatures = [_number(item) for item in TEMPERATURE_PATTERN.findall(text)]
    goods = _label_value(text, "goods")
    vehicle = _label_value(text, "vehicle_type")

    adr: bool | None = None
    if re.search(r"\b(?:kein adr|non[- ]?adr|not adr)\b", text, re.I):
        adr = False
    elif re.search(r"\badr\b", text, re.I):
        adr = True

    return {
        "pickup_location": pickup_location,
        "pickup_date": pickup_date,
        "delivery_location": delivery_location,
        "delivery_date": delivery_date,
        "goods": goods[:120] if goods else None,
        "pallets": int(pallets_match.group(1)) if pallets_match else None,
        "weight_kg": weight_kg,
        "loading_meters": _number(ldm_match.group(1)) if ldm_match else None,
        "vehicle_type": vehicle[:120] if vehicle else None,
        "temperature_min_c": min(temperatures) if temperatures else None,
        "temperature_max_c": max(temperatures) if temperatures else None,
        "adr": adr,
    }


def classify(email: EmailData, required_fields: list[str], thresholds: dict[str, int]) -> ParseResult:
    text = f"{email.subject}\n{email.current_body}"[:30000]
    price_score, price_matches = _score(text, PRICE_RULES)
    booking_score, booking_matches = _score(text, BOOKING_RULES)
    status_score, status_matches = _score(text, STATUS_RULES)

    if ROUTE_HINT.search(text):
        price_score += 1
        price_matches.append("transportrelation (+1)")

    scores = {"PRICE_REQUEST": price_score, "BOOKING": booking_score, "STATUS_UPDATE": status_score}
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_category, best_score = ordered[0]
    second_score = ordered[1][1]
    unclear_margin = int(thresholds.get("unclear_margin", 1))

    minimum = {
        "PRICE_REQUEST": int(thresholds.get("price_request", 4)),
        "BOOKING": int(thresholds.get("booking", 4)),
        "STATUS_UPDATE": int(thresholds.get("status_update", 4)),
    }

    if best_score < minimum[best_category]:
        category = "OTHER" if best_score == 0 else "UNCLEAR"
    elif best_score - second_score <= unclear_margin and second_score > 0:
        category = "UNCLEAR"
    else:
        category = best_category

    matched_rules = [*price_matches, *booking_matches, *status_matches]
    attachment_relevant = bool(email.attachment_names and ATTACHMENT_HINT.search(text))
    shipment = extract_shipment(text) if category in {"PRICE_REQUEST", "UNCLEAR"} else {}
    shipments = [shipment] if shipment and any(value is not None for value in shipment.values()) else []

    missing_fields: list[str] = []
    if category == "PRICE_REQUEST":
        if not shipments:
            missing_fields.append("shipments")
        else:
            for field in required_fields:
                if not shipments[0].get(field):
                    missing_fields.append(field)

    ambiguities: list[str] = []
    if category == "UNCLEAR":
        ambiguities.append("Regeln liefern kein eindeutiges Klassifikationsergebnis.")
    if attachment_relevant:
        ambiguities.append("Wesentliche Angaben könnten ausschließlich im Anhang stehen.")

    if category == "PRICE_REQUEST":
        route = "review" if attachment_relevant else ("complete" if not missing_fields else "incomplete")
    elif category == "UNCLEAR":
        route = "review"
    else:
        route = "not_request"

    if best_score == 0:
        confidence = 0.90
    else:
        separation = max(0, best_score - second_score)
        confidence = min(0.98, 0.55 + 0.06 * best_score + 0.04 * separation)
        if category == "UNCLEAR":
            confidence = min(confidence, 0.65)

    return ParseResult(
        category=category,
        confidence=round(confidence, 3),
        route=route,
        shipments=shipments,
        missing_fields=missing_fields,
        ambiguities=ambiguities,
        attachment_relevant=attachment_relevant,
        matched_rules=matched_rules,
        scores=scores,
    )
