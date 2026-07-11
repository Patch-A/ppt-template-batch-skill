from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from import_content_document import load_source, paragraph_records


FIELD_ALIASES = {
    "name": {"name", "company", "company_name", "buyer", "enterprise", "\u4f01\u4e1a", "\u4f01\u4e1a\u540d\u79f0", "\u516c\u53f8", "\u516c\u53f8\u540d\u79f0", "\u4e70\u5bb6"},
    "country": {"country", "region", "market", "\u56fd\u5bb6", "\u5730\u533a", "\u6240\u5728\u56fd", "\u5e02\u573a"},
    "website": {"website", "site", "url", "web", "\u7f51\u7ad9", "\u5b98\u7f51", "\u7f51\u5740", "\u4f01\u4e1a\u5b98\u7f51"},
    "products": {"products", "product", "procurement", "procurement_need", "need", "demand", "\u91c7\u8d2d\u4ea7\u54c1", "\u91c7\u8d2d\u9700\u6c42", "\u4ea7\u54c1", "\u9700\u6c42", "\u91c7\u8d2d\u54c1\u7c7b"},
    "bio": {"bio", "summary", "intro", "introduction", "description", "profile", "content", "\u7b80\u4ecb", "\u4f01\u4e1a\u7b80\u4ecb", "\u516c\u53f8\u7b80\u4ecb", "\u4ecb\u7ecd", "\u63cf\u8ff0", "\u5185\u5bb9"},
}


def normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(value or "").strip().lower())


def canonical_field(key: Any) -> str | None:
    normalized = normalize_key(key)
    for field, aliases in FIELD_ALIASES.items():
        if normalized in {normalize_key(alias) for alias in aliases}:
            return field
    return None


def source_records(raw_text: str, parsed: Any | None) -> list[dict[str, Any]]:
    if isinstance(parsed, dict):
        values = parsed.get("records") if isinstance(parsed.get("records"), list) else [parsed]
    elif isinstance(parsed, list):
        values = parsed
    else:
        values = paragraph_records(raw_text)
    return [item for item in values if isinstance(item, dict)]


def normalize_record(item: dict[str, Any], default_country: str) -> dict[str, str]:
    normalized = {"name": "", "country": default_country, "website": "", "products": "", "bio": ""}
    extra_text: list[str] = []
    for key, value in item.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        text = str(value or "").strip()
        if not text:
            continue
        field = canonical_field(key)
        if field:
            normalized[field] = text
        elif key == "title" and not normalized["name"]:
            normalized["name"] = text
        else:
            extra_text.append(text)
    if not normalized["bio"] and extra_text:
        normalized["bio"] = "\n".join(extra_text)
    return normalized


def parse_buyers(raw_text: str, parsed: Any | None, default_country: str) -> list[dict[str, str]]:
    buyers = [normalize_record(item, default_country) for item in source_records(raw_text, parsed)]
    return [buyer for buyer in buyers if any(buyer.values())]


def main() -> int:
    parser = argparse.ArgumentParser(description="Recognize pasted or uploaded buyer data into buyer-board fields.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--country", default="")
    parser.add_argument("--procurement-need", default="")
    args = parser.parse_args()

    raw_text, parsed = load_source(Path(args.input))
    payload = {
        "globals": {
            "country": args.country.strip(),
            "procurement_need": args.procurement_need.strip(),
            "source_text": raw_text,
        },
        "records": parse_buyers(raw_text, parsed, args.country.strip()),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
