from __future__ import annotations

import argparse
from collections import Counter
import json
import re
from pathlib import Path
from typing import Any


DEFAULT_EDITABLE_FIELDS = ("bio", "summary", "intro", "description", "body", "copy")
ANCHOR_FIELDS = ("name", "country", "website")
FORBIDDEN_CUSTOMER_TERMS = (
    "buyer_id",
    "accepted",
    "internal library",
    "public candidate",
    "verification",
    "pending verification",
    "weak match",
    "scraping failed",
    "内部库",
    "候选池",
    "待核验",
    "弱相关",
    "抓取失败",
)
FACT_TOKEN_PATTERN = re.compile(
    r"https?://[^\s，。；]+|www\.[^\s，。；]+|"
    r"(?<![A-Za-z0-9])(?:[$¥￥€£]?\d[\d,.]*(?:%|％|年|月|日|家|个|项|台|套|人|万元|亿元|万美元|亿美元)?)"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def format_path(parts: tuple[str, ...]) -> str:
    if not parts:
        return "$"
    output = "$"
    for part in parts:
        output += f"[{part}]" if part.isdigit() else f".{part}"
    return output


def normalized_fact_tokens(text: str) -> Counter[str]:
    return Counter(match.group(0).strip().lower() for match in FACT_TOKEN_PATTERN.finditer(text))


def sibling_anchors(record: dict[str, Any], original_text: str) -> list[str]:
    anchors: list[str] = []
    for field in ANCHOR_FIELDS:
        value = str(record.get(field) or "").strip()
        if value and value in original_text:
            anchors.append(value)
    return anchors


def validate_editable_text(
    before: str,
    after: str,
    record: dict[str, Any],
    path: tuple[str, ...],
    max_expansion_ratio: float,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    display_path = format_path(path)
    if before and not after.strip():
        issues.append({"path": display_path, "code": "editable_text_cleared"})
        return issues

    before_tokens = normalized_fact_tokens(before)
    after_tokens = normalized_fact_tokens(after)
    if before_tokens != after_tokens:
        issues.append(
            {
                "path": display_path,
                "code": "fact_tokens_changed",
                "detail": f"before={dict(before_tokens)} after={dict(after_tokens)}",
            }
        )

    for anchor in sibling_anchors(record, before):
        if anchor not in after:
            issues.append(
                {
                    "path": display_path,
                    "code": "identity_anchor_removed",
                    "detail": anchor,
                }
            )

    lowered = after.lower()
    for term in FORBIDDEN_CUSTOMER_TERMS:
        if term.lower() in lowered:
            issues.append(
                {"path": display_path, "code": "forbidden_customer_term", "detail": term}
            )

    if before and len(after) > max(1, int(len(before) * max_expansion_ratio)):
        issues.append(
            {
                "path": display_path,
                "code": "copy_expanded_too_far",
                "detail": f"before={len(before)} after={len(after)} ratio={max_expansion_ratio}",
            }
        )
    return issues


def compare_payloads(
    before: Any,
    after: Any,
    editable_fields: frozenset[str],
    max_expansion_ratio: float,
    path: tuple[str, ...] = (),
    record: dict[str, Any] | None = None,
) -> tuple[list[dict[str, str]], list[str]]:
    issues: list[dict[str, str]] = []
    changed_fields: list[str] = []

    if type(before) is not type(after):
        return ([{"path": format_path(path), "code": "type_changed"}], changed_fields)

    if isinstance(before, dict):
        if before.keys() != after.keys():
            issues.append(
                {
                    "path": format_path(path),
                    "code": "object_keys_changed",
                    "detail": f"before={sorted(before)} after={sorted(after)}",
                }
            )
            return issues, changed_fields
        current_record = before
        for key in before:
            child_path = path + (key,)
            if key in editable_fields:
                if not isinstance(before[key], str) or not isinstance(after[key], str):
                    issues.append({"path": format_path(child_path), "code": "editable_field_not_string"})
                    continue
                if before[key] != after[key]:
                    changed_fields.append(format_path(child_path))
                    issues.extend(
                        validate_editable_text(
                            before[key],
                            after[key],
                            current_record,
                            child_path,
                            max_expansion_ratio,
                        )
                    )
                continue
            child_issues, child_changes = compare_payloads(
                before[key],
                after[key],
                editable_fields,
                max_expansion_ratio,
                child_path,
                current_record,
            )
            issues.extend(child_issues)
            changed_fields.extend(child_changes)
        return issues, changed_fields

    if isinstance(before, list):
        if len(before) != len(after):
            return (
                [
                    {
                        "path": format_path(path),
                        "code": "list_length_changed",
                        "detail": f"before={len(before)} after={len(after)}",
                    }
                ],
                changed_fields,
            )
        for index, (before_item, after_item) in enumerate(zip(before, after)):
            child_issues, child_changes = compare_payloads(
                before_item,
                after_item,
                editable_fields,
                max_expansion_ratio,
                path + (str(index),),
                record,
            )
            issues.extend(child_issues)
            changed_fields.extend(child_changes)
        return issues, changed_fields

    if before != after:
        issues.append(
            {
                "path": format_path(path),
                "code": "protected_value_changed",
                "detail": f"before={before!r} after={after!r}",
            }
        )
    return issues, changed_fields


def parse_editable_fields(value: str) -> frozenset[str]:
    fields = frozenset(item.strip() for item in value.split(",") if item.strip())
    if not fields:
        raise argparse.ArgumentTypeError("at least one editable field is required")
    return fields


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a batch copy rewrite without allowing facts or record structure to change."
    )
    parser.add_argument("--before", required=True, type=Path, help="Verified JSON before copy rewriting")
    parser.add_argument("--after", required=True, type=Path, help="Rewritten JSON to validate")
    parser.add_argument(
        "--editable-fields",
        type=parse_editable_fields,
        default=frozenset(DEFAULT_EDITABLE_FIELDS),
        help="Comma-separated natural-language fields allowed to change",
    )
    parser.add_argument("--report", type=Path, help="Optional JSON validation report")
    parser.add_argument(
        "--max-expansion-ratio",
        type=float,
        default=1.25,
        help="Maximum rewritten/original character ratio for non-empty fields",
    )
    args = parser.parse_args()
    if args.max_expansion_ratio < 1:
        parser.error("--max-expansion-ratio must be at least 1")

    before = load_json(args.before)
    after = load_json(args.after)
    issues, changed_fields = compare_payloads(
        before,
        after,
        args.editable_fields,
        args.max_expansion_ratio,
    )
    report = {
        "ok": not issues,
        "editable_fields": sorted(args.editable_fields),
        "changed_fields": changed_fields,
        "issues": issues,
    }
    if args.report:
        save_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
