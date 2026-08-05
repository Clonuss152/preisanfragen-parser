from __future__ import annotations

import csv
from pathlib import Path


def load_customers(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    customers: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            domain = (row.get("domain") or "").strip().lower().lstrip("@")
            company = (row.get("company") or "").strip()
            if domain and company:
                customers[domain] = company
    return customers


def identify_company(sender_domain: str | None, customers: dict[str, str]) -> str | None:
    if not sender_domain:
        return None
    domain = sender_domain.lower()
    if domain in customers:
        return customers[domain]
    # Allows subdomains such as logistics.customer.com.
    matches = [(known, company) for known, company in customers.items() if domain.endswith("." + known)]
    if not matches:
        return None
    return max(matches, key=lambda item: len(item[0]))[1]
