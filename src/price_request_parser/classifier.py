from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol

from .models import EmailData, ModelUsage, ParseResult


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "category": {
            "type": "string",
            "enum": ["PRICE_REQUEST", "BOOKING", "STATUS_UPDATE", "OTHER", "UNCLEAR"],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "needs_fallback": {"type": "boolean"},
        "attachment_relevant": {"type": "boolean"},
        "shipments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "pickup_location": {"type": ["string", "null"]},
                    "pickup_country": {"type": ["string", "null"]},
                    "pickup_date": {"type": ["string", "null"]},
                    "pickup_time": {"type": ["string", "null"]},
                    "delivery_location": {"type": ["string", "null"]},
                    "delivery_country": {"type": ["string", "null"]},
                    "delivery_date": {"type": ["string", "null"]},
                    "delivery_time": {"type": ["string", "null"]},
                    "goods": {"type": ["string", "null"]},
                    "pallets": {"type": ["integer", "null"]},
                    "weight_kg": {"type": ["number", "null"]},
                    "loading_meters": {"type": ["number", "null"]},
                    "vehicle_type": {"type": ["string", "null"]},
                    "temperature_min_c": {"type": ["number", "null"]},
                    "temperature_max_c": {"type": ["number", "null"]},
                    "adr": {"type": ["boolean", "null"]},
                    "notes": {"type": ["string", "null"]},
                },
                "required": [
                    "pickup_location", "pickup_country", "pickup_date", "pickup_time",
                    "delivery_location", "delivery_country", "delivery_date", "delivery_time",
                    "goods", "pallets", "weight_kg", "loading_meters", "vehicle_type",
                    "temperature_min_c", "temperature_max_c", "adr", "notes"
                ],
            },
        },
        "missing_fields": {"type": "array", "items": {"type": "string"}},
        "ambiguities": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "category", "confidence", "needs_fallback", "attachment_relevant",
        "shipments", "missing_fields", "ambiguities"
    ],
}

SYSTEM_INSTRUCTIONS = """You classify and extract freight transport emails.
PRICE_REQUEST means the sender requests a freight rate, price, offer, quotation, or capacity with pricing.
BOOKING means a transport is awarded/booked without asking for a price. STATUS_UPDATE is operational status only.
Extract every shipment in the current email. Never invent values. Use null when absent. Dates must be YYYY-MM-DD when the year is known; otherwise keep a short unambiguous source form. Weight is kg.
Set needs_fallback=true only when more email context could resolve classification or extraction uncertainty. Missing data alone is not a fallback reason.
Set attachment_relevant=true when essential request details appear to be only in an attachment. Keep ambiguities and missing_fields short."""


class Classifier(Protocol):
    def classify(self, email: EmailData, model: str, include_history: bool, max_chars: int) -> tuple[ParseResult, ModelUsage]: ...


def _payload(email: EmailData, include_history: bool, max_chars: int) -> str:
    body = email.current_body[:max_chars]
    data: dict[str, Any] = {
        "sender_email": email.sender_email,
        "known_company": email.customer_company,
        "subject": email.subject,
        "body": body,
        "attachment_names": email.attachment_names,
    }
    if include_history and email.quoted_history:
        remaining = max(0, max_chars - len(body))
        data["quoted_history"] = email.quoted_history[:remaining]
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


class OpenAIClassifier:
    def __init__(self, pricing: dict[str, dict[str, float]]) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set. Use --mock for a local test.")
        from openai import OpenAI
        self.client = OpenAI()
        self.pricing = pricing

    def classify(self, email: EmailData, model: str, include_history: bool, max_chars: int) -> tuple[ParseResult, ModelUsage]:
        response = self.client.responses.create(
            model=model,
            instructions=SYSTEM_INSTRUCTIONS,
            input=_payload(email, include_history, max_chars),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "freight_price_request",
                    "strict": True,
                    "schema": OUTPUT_SCHEMA,
                },
                "verbosity": "low",
            },
            max_output_tokens=1200,
            store=False,
        )
        parsed = json.loads(response.output_text)
        input_tokens = int(getattr(response.usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(response.usage, "output_tokens", 0) or 0)
        rates = self.pricing.get(model, {})
        cost = (input_tokens * float(rates.get("input", 0)) + output_tokens * float(rates.get("output", 0))) / 1_000_000
        usage = ModelUsage(model=model, input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost_usd=cost)
        result = ParseResult(
            category=parsed["category"],
            confidence=float(parsed["confidence"]),
            needs_fallback=bool(parsed["needs_fallback"]),
            attachment_relevant=bool(parsed["attachment_relevant"]),
            shipments=list(parsed["shipments"]),
            missing_fields=list(parsed["missing_fields"]),
            ambiguities=list(parsed["ambiguities"]),
            model_used=model,
        )
        return result, usage


class MockClassifier:
    """Cheap local smoke test. It is deliberately simple and not a replacement for the API."""

    PRICE_WORDS = re.compile(r"(?i)\b(preis|angebot|rate|quote|quotation|cost|kosten|frachtsatz)\w*\b")
    BOOKING_WORDS = re.compile(r"(?i)\b(beauftragen|auftrag|book(?:ing)?|please arrange|fix)\w*\b")
    DATE = re.compile(r"\b(\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?)\b")
    POSTAL_CITY = re.compile(r"\b([A-Z]{0,2}-?\d{4,5})\s+([A-Za-zÄÖÜäöüß .'-]{2,40})")

    def classify(self, email: EmailData, model: str, include_history: bool, max_chars: int) -> tuple[ParseResult, ModelUsage]:
        text = f"{email.subject}\n{email.current_body}"
        if include_history:
            text += "\n" + email.quoted_history
        category = "PRICE_REQUEST" if self.PRICE_WORDS.search(text) else "BOOKING" if self.BOOKING_WORDS.search(text) else "OTHER"
        locations = [f"{m.group(1)} {m.group(2).strip()}" for m in self.POSTAL_CITY.finditer(text)]
        dates = self.DATE.findall(text)
        shipment = {
            "pickup_location": locations[0] if len(locations) > 0 else None,
            "pickup_country": None,
            "pickup_date": dates[0] if len(dates) > 0 else None,
            "pickup_time": None,
            "delivery_location": locations[1] if len(locations) > 1 else None,
            "delivery_country": None,
            "delivery_date": dates[1] if len(dates) > 1 else None,
            "delivery_time": None,
            "goods": None,
            "pallets": None,
            "weight_kg": None,
            "loading_meters": None,
            "vehicle_type": None,
            "temperature_min_c": None,
            "temperature_max_c": None,
            "adr": None,
            "notes": "Mock result",
        }
        result = ParseResult(
            category=category,
            confidence=0.90 if category != "OTHER" else 0.75,
            needs_fallback=False,
            attachment_relevant=False,
            shipments=[shipment] if category in {"PRICE_REQUEST", "BOOKING"} else [],
            missing_fields=[],
            ambiguities=[],
            model_used=f"mock:{model}",
        )
        return result, ModelUsage(model=f"mock:{model}", input_tokens=0, output_tokens=0, estimated_cost_usd=0.0)
