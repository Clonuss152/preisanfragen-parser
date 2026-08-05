from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .classifier import MockClassifier, OpenAIClassifier
from .cleaner import parse_email_file
from .customer_lookup import identify_company, load_customers
from .routing import apply_business_rules, should_fallback


def _load_config(project_root: Path) -> dict[str, Any]:
    with (project_root / "config.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _safe_stem(path: Path) -> str:
    digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:8]
    return f"{path.stem}_{digest}"


def _write_outputs(project_root: Path, source: Path, email: Any, result: Any, config: dict[str, Any]) -> Path:
    output_root = project_root / config["output_dir"]
    route_dir = output_root / (result.route or "error")
    route_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(source)

    destination = route_dir / source.name
    if config.get("move_originals", False):
        shutil.move(str(source), destination)
    else:
        shutil.copy2(source, destination)

    record = {
        "processed_at_utc": datetime.now(timezone.utc).isoformat(),
        "email": email.to_dict(),
        "result": result.to_dict(),
        "total_estimated_cost_usd": round(sum(item.estimated_cost_usd for item in result.usage), 10),
    }
    (route_dir / f"{stem}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    if config.get("save_cleaned_text", True):
        cleaned = (
            f"From: {email.sender_email or ''}\n"
            f"Company: {email.customer_company or ''}\n"
            f"Subject: {email.subject}\n\n"
            f"{email.current_body}\n"
        )
        (route_dir / f"{stem}.cleaned.txt").write_text(cleaned, encoding="utf-8")
    return route_dir


def process_file(project_root: Path, path: Path, config: dict[str, Any], mock: bool) -> tuple[str, float]:
    email = parse_email_file(path)
    customers = load_customers(project_root / config["customers_file"])
    email.customer_company = identify_company(email.sender_domain, customers)

    classifier = MockClassifier() if mock else OpenAIClassifier(config.get("pricing_usd_per_million_tokens", {}))
    primary_model = config["models"]["primary"]
    fallback_model = config["models"]["fallback"]

    result, usage = classifier.classify(
        email=email,
        model=primary_model,
        include_history=False,
        max_chars=int(config.get("max_body_chars_primary", 12000)),
    )
    result.usage.append(usage)

    if should_fallback(result, float(config.get("confidence_threshold", 0.80))):
        fallback_result, fallback_usage = classifier.classify(
            email=email,
            model=fallback_model,
            include_history=True,
            max_chars=int(config.get("max_body_chars_fallback", 50000)),
        )
        fallback_result.fallback_used = True
        fallback_result.usage = [*result.usage, fallback_usage]
        result = fallback_result

    result = apply_business_rules(result, list(config.get("required_shipment_fields", [])))
    route_dir = _write_outputs(project_root, path, email, result, config)
    total_cost = sum(item.estimated_cost_usd for item in result.usage)
    print(f"{path.name}: {result.category} -> {result.route} | model={result.model_used} | cost=${total_cost:.8f} | {route_dir}")
    return result.route or "error", total_cost


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify and extract freight price-request emails.")
    parser.add_argument("paths", nargs="*", help=".eml or .txt files. Defaults to all files in input/.")
    parser.add_argument("--mock", action="store_true", help="Run a local heuristic smoke test without API calls.")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    config = _load_config(project_root)
    if args.paths:
        files = [Path(item).resolve() for item in args.paths]
    else:
        input_dir = project_root / config["input_dir"]
        files = sorted([*input_dir.glob("*.eml"), *input_dir.glob("*.txt")])

    if not files:
        print("No .eml or .txt files found.", file=sys.stderr)
        return 1

    counts: dict[str, int] = {}
    total_cost = 0.0
    failures = 0
    for path in files:
        try:
            route, cost = process_file(project_root, path, config, args.mock)
            counts[route] = counts.get(route, 0) + 1
            total_cost += cost
        except Exception as exc:
            failures += 1
            print(f"ERROR {path}: {exc}", file=sys.stderr)

    print(f"Summary: {counts}; failures={failures}; estimated API cost=${total_cost:.8f}")
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
