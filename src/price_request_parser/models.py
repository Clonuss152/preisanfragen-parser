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
class ModelUsage:
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ParseResult:
    category: str
    confidence: float
    needs_fallback: bool
    attachment_relevant: bool
    shipments: list[dict[str, Any]]
    missing_fields: list[str]
    ambiguities: list[str]
    model_used: str
    fallback_used: bool = False
    route: str | None = None
    usage: list[ModelUsage] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["usage"] = [item.to_dict() for item in self.usage]
        return data
