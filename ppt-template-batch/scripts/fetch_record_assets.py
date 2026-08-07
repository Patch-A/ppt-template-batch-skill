from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import fetch_buyer_assets as asset_fetcher


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def unpack_records(payload: Any) -> tuple[list[dict[str, Any]], str]:
    if isinstance(payload, list):
        return [dict(item) for item in payload], "list"
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return [dict(item) for item in payload["records"]], "object"
    raise ValueError("records JSON must be a list or an object with a records list")


def repack_records(payload: Any, records: list[dict[str, Any]], shape: str) -> Any:
    if shape == "list":
        return records
    result = dict(payload)
    result["records"] = records
    return result


def process_record(
    record: dict[str, Any],
    url_field: str,
    label_field: str,
    logo_field: str,
    visual_field: str,
    assets_dir: Path,
    cache: dict[str, Any],
    asset_mode: str,
    crawl_timeout_ms: int,
    per_record_seconds: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    enriched = dict(record)
    url = str(record.get(url_field) or "").strip()
    label = str(record.get(label_field) or record.get("name") or "record").strip()
    if not url:
        enriched["asset_fetch_notes"] = f"missing_url_field:{url_field}"
        return enriched, {
            "label": label,
            "url": "",
            "asset_mode": asset_mode,
            "logo_hit": False,
            "site_hit": False,
            "notes": [f"missing_url_field:{url_field}"],
        }

    canonical = dict(enriched)
    canonical["name"] = str(canonical.get("name") or label)
    canonical["website"] = url
    previous_deadline = asset_fetcher.FETCH_DEADLINE
    asset_fetcher.FETCH_DEADLINE = time.monotonic() + max(10, int(per_record_seconds))
    try:
        processed, report = asset_fetcher.process_buyer(
            canonical, assets_dir, cache, False, asset_mode, crawl_timeout_ms
        )
    finally:
        asset_fetcher.FETCH_DEADLINE = previous_deadline

    enriched[logo_field] = processed.get("logo_path", "")
    enriched[visual_field] = processed.get("site_image_path", "")
    enriched["asset_fetch_notes"] = processed.get("asset_fetch_notes", "")
    report = dict(report)
    report.update(
        {
            "label": label,
            "url": url,
            "url_field": url_field,
            "logo_field": logo_field,
            "visual_field": visual_field,
        }
    )
    return enriched, report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch verified website logo and visual assets for generic PPT records."
    )
    parser.add_argument("--records", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--assets-dir", required=True)
    parser.add_argument("--cache-file", required=True)
    parser.add_argument("--report-file", required=True)
    parser.add_argument("--url-field", default="website")
    parser.add_argument("--label-field", default="name")
    parser.add_argument("--logo-field", default="logo_path")
    parser.add_argument("--visual-field", default="site_image_path")
    parser.add_argument(
        "--asset-mode",
        choices=("light", "auto", "browser", "crawl4ai"),
        default="light",
    )
    parser.add_argument("--browser-timeout-ms", type=int, default=8000)
    parser.add_argument("--per-record-seconds", type=int, default=35)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = load_json(Path(args.records))
    records, shape = unpack_records(source)
    assets_dir = Path(args.assets_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)
    cache_path = Path(args.cache_file)
    cache = asset_fetcher.load_cache(cache_path)
    enriched: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        try:
            item, report = process_record(
                record,
                args.url_field,
                args.label_field,
                args.logo_field,
                args.visual_field,
                assets_dir,
                cache,
                args.asset_mode,
                args.browser_timeout_ms,
                args.per_record_seconds,
            )
        except Exception as exc:
            item = dict(record)
            item["asset_fetch_notes"] = f"asset_fetch_failed:{exc.__class__.__name__}"
            report = {
                "label": str(record.get(args.label_field) or "record"),
                "url": str(record.get(args.url_field) or ""),
                "asset_mode": args.asset_mode,
                "ok": False,
                "error": str(exc),
            }
        report["record_index"] = index
        enriched.append(item)
        reports.append(report)
    asset_fetcher.save_cache(cache_path, cache)
    save_json(Path(args.output), repack_records(source, enriched, shape))
    save_json(Path(args.report_file), reports)
    print(args.output)
    print(args.report_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
