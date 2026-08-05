from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .models import EmailData, ParseResult

# Strong request phrases receive most points. Generic transport facts only support a decision.
PRICE_RULES: list[tuple[str, re.Pattern[str], int]] = [
    ("de_preisanfrage", re.compile(r"\b(?:preisanfrage|preisangebot|frachtanfrage|transportanfrage|offertanfrage)\b", re.I), 45),
    ("de_bitte_preis", re.compile(r"\b(?:bitte|könnt(?:en)?\s+sie|kannst\s+du).{0,55}\b(?:preis|angebot|offerte|frachtrate)\b", re.I | re.S), 40),
    ("de_was_kostet", re.compile(r"\b(?:was kostet|zu welchem preis|welchen preis|ihren besten preis|eure beste rate)\b", re.I), 45),
    ("en_rfq", re.compile(r"\b(?:rfq|request for quotation|request for quote|rate request|freight rate request|transport rate request)\b", re.I), 50),
    ("en_please_quote", re.compile(r"\b(?:please|kindly).{0,35}\b(?:quote|provide|send).{0,40}\b(?:rate|price|quotation|offer)?\b", re.I | re.S), 45),
    ("en_can_you_quote", re.compile(r"\b(?:can|could|would)\s+you.{0,40}\b(?:quote|offer|provide).{0,40}\b(?:rate|price|quotation|transport)?\b", re.I | re.S), 45),
    ("en_best_rate", re.compile(r"\b(?:best rate|best price|your rate|freight rate|transport rate|rate and availability|price and availability)\b", re.I), 35),
    ("generic_quote", re.compile(r"\b(?:quotation|quote|offerte|frachtrate)\b", re.I), 22),
    ("generic_price", re.compile(r"\b(?:preis|price|rate|angebot|offer)\b", re.I), 12),
]

BOOKING_RULES: list[tuple[str, re.Pattern[str], int]] = [
    ("de_beauftragung", re.compile(r"\b(?:hiermit beauftragen|wir beauftragen|transportauftrag|bitte fest buchen|auftrag ist fix)\b", re.I), 50),
    ("en_booking", re.compile(r"\b(?:we hereby book|please book|booking confirmation|transport is confirmed|shipment is confirmed|please proceed)\b", re.I), 50),
]

STATUS_RULES: list[tuple[str, re.Pattern[str], int]] = [
    ("de_statusfrage", re.compile(r"\b(?:wo ist der lkw|aktueller stand|bitte um status|bitte eta|wann kommt der lkw)\b", re.I), 50),
    ("en_statusfrage", re.compile(r"\b(?:current status|please advise eta|where is the truck|please provide an update|shipment status)\b", re.I), 50),
    ("statusbegriffe", re.compile(r"\b(?:status|eta|verspätung|delay|abgeladen|beladen|delivered|loaded|entladen|unloaded)\b", re.I), 18),
]

NEGATIVE_PRICE_RULES: list[tuple[str, re.Pattern[str], int]] = [
    ("bestehender_preis", re.compile(r"\b(?:vereinbarte[rn]? preis|preis bleibt unverändert|agreed price|price remains unchanged|rate remains unchanged)\b", re.I), -35),
    ("rechnung_preis", re.compile(r"\b(?:rechnung|invoice|credit note|gutschrift).{0,50}\b(?:preis|price|rate)\b", re.I | re.S), -25),
]

ATTACHMENT_HINT = re.compile(r"\b(?:siehe anhang|see attachment|details im anhang|attached request|attached rfq|anbei die anfrage|please find attached)\b", re.I)
ROUTE_HINT = re.compile(r"\b(?:von|abholung|pickup|loading|collection|ladeort)\b.{0,140}\b(?:nach|zustellung|delivery|unloading|destination|entladeort)\b", re.I | re.S)
REQUEST_TONE = re.compile(r"\b(?:bitte|please|kindly|könnt(?:en)?\s+sie|can you|could you|would you)\b", re.I)
TRANSPORT_TERMS = re.compile(r"\b(?:transport|shipment|load|ladung|truck|lkw|trailer|sattelzug|pallets?|paletten|weight|gewicht|pickup|delivery|abholung|zustellung)\b", re.I)

DATE_PATTERN = re.compile(r"\b(\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?)\b")
ISO_DATE_PATTERN = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
POSTCODE_CITY_PATTERN = re.compile(r"\b(?:(?P<country>[A-Z]{2})[- ]?)?(?P<postcode>\d{4,5})\s+(?P<city>[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\- ]{2,40})")
WEIGHT_PATTERN = re.compile(r"\b(\d{1,3}(?:[.,]\d{3})*|\d+(?:[.,]\d+)?)\s*(kg|kgs|t|to|tonnen|tons?|tonnes?)\b", re.I)
PALLET_PATTERN = re.compile(r"\b(\d{1,3})\s*(?:euro[- ]?)?(?:paletten|pallets?|plt|plts|pl)\b", re.I)
LDM_PATTERN = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(?:ldm|lademeter|loading meters?)\b", re.I)
TEMPERATURE_PATTERN = re.compile(r"(?<!\d)(-?\d{1,2}(?:[.,]\d+)?)\s*(?:°\s*)?c\b", re.I)

LABEL_PATTERNS: dict[str, re.Pattern[str]] = {
    "pickup_location": re.compile(r"(?im)^\s*(?:abholung|ladeort|pickup|pick-up|loading|collection|origin)\s*[:\-]\s*(.+)$"),
    "delivery_location": re.compile(r"(?im)^\s*(?:zustellung|entladeort|delivery|unloading|destination|drop-off)\s*[:\-]\s*(.+)$"),
    "pickup_date": re.compile(r"(?im)^\s*(?:abholdatum|ladedatum|pickup date|pick-up date|loading date|collection date)\s*[:\-]\s*(.+)$"),
    "delivery_date": re.compile(r"(?im)^\s*(?:zustelldatum|entladedatum|delivery date|unloading date|drop-off date)\s*[:\-]\s*(.+)$"),
    "goods": re.compile(r"(?im)^\s*(?:ware|goods|commodity|cargo|product)\s*[:\-]\s*(.+)$"),
    "vehicle_type": re.compile(r"(?im)^\s*(?:fahrzeug|vehicle|equipment|truck|trailer type)\s*[:\-]\s*(.+)$"),
}


def _score(text: str, rules: list[tuple[str, re.Pattern[str], int]]) -> tuple[int, list[str]]:
    total = 0
    matches: list[str] = []
    for name, pattern, points in rules:
        if pattern.search(text):
            total += points
            sign = "+" if points >= 0 else ""
            matches.append(f"{name} ({sign}{points})")
    return total, matches


def _clean_location(value: str) -> str:
    value = re.split(r"\s{2,}|;|\|", value.strip())[0]
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

    route = re.search(r"\b(?:von|from)\s+(.{2,80}?)\s+(?:nach|to)\s+(.{2,80}?)(?:[\n,.;]|$)", text, re.I)
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
    value = value.strip()
    # 18,000 / 18.000 are treated as thousands; 18,5 / 18.5 as decimals.
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", value):
        return float(re.sub(r"[.,]", "", value))
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    else:
        value = value.replace(",", ".")
    return float(value)


def extract_shipment(text: str) -> dict[str, Any]:
    pickup_location, delivery_location = _extract_locations(text)
    pickup_date, delivery_date = _extract_dates(text)
    weight_kg: float | None = None
    weight_match = WEIGHT_PATTERN.search(text)
    if weight_match:
        weight_kg = _number(weight_match.group(1))
        if weight_match.group(2).lower() in {"t", "to", "tonnen", "ton", "tons", "tonne", "tonnes"}:
            weight_kg *= 1000

    pallets_match = PALLET_PATTERN.search(text)
    ldm_match = LDM_PATTERN.search(text)
    temperatures = [_number(item) for item in TEMPERATURE_PATTERN.findall(text)]
    goods = _label_value(text, "goods")
    vehicle = _label_value(text, "vehicle_type")
    adr: bool | None = None
    if re.search(r"\b(?:kein adr|non[- ]?adr|not adr|no adr)\b", text, re.I):
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
    negative_score, negative_matches = _score(text, NEGATIVE_PRICE_RULES)
    price_score += negative_score
    booking_score, booking_matches = _score(text, BOOKING_RULES)
    status_score, status_matches = _score(text, STATUS_RULES)

    shipment = extract_shipment(text)
    transport_facts = 0
    if shipment.get("pickup_location") and shipment.get("delivery_location"):
        transport_facts += 18
        price_matches.append("transportrelation (+18)")
    elif ROUTE_HINT.search(text):
        transport_facts += 10
        price_matches.append("transportrelation_hinweis (+10)")
    if shipment.get("pickup_date"):
        transport_facts += 6
        price_matches.append("abholdatum (+6)")
    if shipment.get("weight_kg") is not None:
        transport_facts += 6
        price_matches.append("gewicht (+6)")
    if shipment.get("pallets") is not None:
        transport_facts += 6
        price_matches.append("paletten (+6)")
    if REQUEST_TONE.search(text) and TRANSPORT_TERMS.search(text):
        transport_facts += 8
        price_matches.append("anfrageform_transport (+8)")
    price_score += transport_facts

    scores = {"PRICE_REQUEST": max(0, price_score), "BOOKING": booking_score, "STATUS_UPDATE": status_score}
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_category, best_score = ordered[0]
    second_score = ordered[1][1]
    unclear_margin = int(thresholds.get("unclear_margin", 12))
    minimum = {
        "PRICE_REQUEST": int(thresholds.get("price_request", 55)),
        "BOOKING": int(thresholds.get("booking", 45)),
        "STATUS_UPDATE": int(thresholds.get("status_update", 45)),
    }

    if best_score < minimum[best_category]:
        category = "OTHER" if best_score < int(thresholds.get("review_minimum", 30)) else "UNCLEAR"
    elif best_score - second_score <= unclear_margin and second_score > 0:
        category = "UNCLEAR"
    else:
        category = best_category

    matched_rules = [*price_matches, *negative_matches, *booking_matches, *status_matches]
    attachment_relevant = bool(email.attachment_names and ATTACHMENT_HINT.search(text))
    shipments = [shipment] if category in {"PRICE_REQUEST", "UNCLEAR"} and any(value is not None for value in shipment.values()) else []

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
        ambiguities.append("Das Regelwerk erkennt Hinweise, aber keine eindeutige Kategorie.")
    if attachment_relevant:
        ambiguities.append("Wesentliche Angaben könnten ausschließlich im Anhang stehen.")

    if category == "PRICE_REQUEST":
        route = "review" if attachment_relevant else ("complete" if not missing_fields else "incomplete")
    elif category == "UNCLEAR":
        route = "review"
    else:
        route = "not_request"

    if category == "OTHER" and best_score == 0:
        confidence = 0.92
    elif category == "UNCLEAR":
        confidence = min(0.69, 0.45 + best_score / 250)
    else:
        confidence = min(0.99, 0.58 + best_score / 180 + max(0, best_score - second_score) / 500)

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
        engine="rule-based-v2.1-de-en",
    )
