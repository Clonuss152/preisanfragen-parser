from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class EmailData:
    source_path: str
    message_id: str | None
    sender_name: str | None
    sender_email: str | None
    sender_domain: str | None
    subject: str
    current_body: str
    quoted_history: str
    attachment_names: list[str] = field(default_factory=list)
    customer_company: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ParseResult:
    category: str
    confidence: float
    route: str
    shipments: list[dict[str, Any]]
    missing_fields: list[str]
    ambiguities: list[str]
    attachment_relevant: bool
    matched_rules: list[str]
    scores: dict[str, int]
    engine: str = "rule-based-v2.1-de-en"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
