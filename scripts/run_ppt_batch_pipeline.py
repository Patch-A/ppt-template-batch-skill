from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def skill_root() -> Path:
    return repo_root() / "ppt-template-batch"


def decode_output(data: bytes | None) -> str:
    if not data:
        return ""
    for encoding in ("utf-8", "gbk", sys.getdefaultencoding()):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def report_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return stat.st_mtime_ns, stat.st_size


def run(cmd: list[str]) -> tuple[str, str]:
    result = subprocess.run(cmd, capture_output=True, text=False)
    stdout = decode_output(result.stdout)
    stderr = decode_output(result.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}")
    return stdout, stderr


def fill_script() -> Path:
    return skill_root() / "scripts" / "fill_ppt_from_records.py"


def run_single_job(job: dict[str, Any], default_args: argparse.Namespace, index: int) -> dict[str, Any]:
    template = job.get("template") or default_args.template
    records = job.get("records") or default_args.records
    layout_config = job.get("layout_config") or job.get("layout-config") or default_args.layout_config
    output = job.get("output") or default_args.output

    if not output and default_args.output_dir:
        records_stem = Path(records).stem if records else f"job-{index:03d}"
        output = str(Path(default_args.output_dir) / f"{records_stem}.pptx")

    missing = [name for name, value in {"template": template, "records": records, "layout_config": layout_config, "output": output}.items() if not value]
    if missing:
        raise ValueError(f"Job {index} is missing required value(s): {', '.join(missing)}")

    workspace_root = Path(job.get("workspace") or default_args.workspace or Path(output).parent / "_workspace")
    workspace = workspace_root / f"job-{index:03d}"
    report_path = Path(job.get("report") or workspace / "fill_report.json")

    cmd = [
        sys.executable,
        str(fill_script()),
        "--template",
        str(template),
        "--records",
        str(records),
        "--layout-config",
        str(layout_config),
        "--output",
        str(output),
        "--workspace",
        str(workspace),
        "--report",
        str(report_path),
    ]
    if default_args.strict or job.get("strict"):
        cmd.append("--strict")

    previous_report_signature = report_signature(report_path)
    try:
        run(cmd)
    except RuntimeError:
        # The filler writes its structured report before returning a strict
        # validation failure. Preserve that report so non-strict batches can
        # continue and callers can see the failed records.
        if report_signature(report_path) in (None, previous_report_signature):
            raise
        report = load_json(report_path)
        if report.get("ok", True):
            raise
    current_report_signature = report_signature(report_path)
    if current_report_signature is None:
        raise RuntimeError(f"Filler completed without writing a report: {report_path}")
    if current_report_signature == previous_report_signature:
        raise RuntimeError(f"Filler did not write a fresh report: {report_path}")
    report = load_json(report_path) if report_path.exists() else {}
    return {
        "index": index,
        "ok": bool(report.get("ok", True)),
        "error_type": report.get("error_type"),
        "error": report.get("error"),
        "schema_version": report.get("schema_version"),
        "template": str(template),
        "records": str(records),
        "layout_config": str(layout_config),
        "output": str(output),
        "report": str(report_path),
        "slide_count": report.get("slide_count"),
        "record_count": report.get("record_count"),
        "processed_record_count": report.get("processed_record_count"),
        "missing_required_fields": report.get("missing_required_fields", []),
        "missing_assets": report.get("missing_assets", []),
        "failed_records": report.get("failed_records", []),
        "stale_template_text": report.get("stale_template_text", []),
        "capacity_warnings": report.get("capacity_warnings", []),
        "warnings": report.get("warnings", []),
        "expected_slide_count": report.get("expected_slide_count"),
        "reopen_ok": report.get("reopen_ok"),
        "reopen_status": report.get("reopen_status", {}),
    }


def normalize_batch(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload]
    if isinstance(payload, dict) and isinstance(payload.get("jobs"), list):
        return [dict(item) for item in payload["jobs"]]
    raise ValueError("batch JSON must be a list or an object with a jobs list.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the generic PPT template batch pipeline.")
    parser.add_argument("--template", help="Template PPTX path")
    parser.add_argument("--records", help="records.json path")
    parser.add_argument("--layout-config", "--config", dest="layout_config", help="layout-config.json path")
    parser.add_argument("--output", help="Single output PPTX path")
    parser.add_argument("--output-dir", help="Output directory for batch jobs without explicit output")
    parser.add_argument("--batch", help="Optional batch.json with multiple jobs")
    parser.add_argument("--workspace", help="Workspace directory for reports and temporary assets")
    parser.add_argument("--report", help="Batch report JSON path")
    parser.add_argument("--strict", action="store_true", help="Fail when a job has missing required fields.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch:
        jobs = normalize_batch(load_json(Path(args.batch)))
    else:
        jobs = [{}]

    results: list[dict[str, Any]] = []
    for index, job in enumerate(jobs, start=1):
        try:
            result = run_single_job(job, args, index)
            results.append(result)
            if (args.strict or job.get("strict")) and not result.get("ok", False):
                break
        except Exception as exc:
            results.append(
                {
                    "index": index,
                    "ok": False,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                    "output": str(job.get("output") or args.output or ""),
                }
            )
            if args.strict:
                break

    report = {
        "ok": all(item.get("ok", False) for item in results),
        "job_count": len(results),
        "jobs": results,
    }
    report_path = Path(args.report) if args.report else Path(args.workspace or "output") / "ppt_batch_report.json"
    write_json(report_path, report)

    for item in results:
        if item.get("output"):
            print(item["output"])
    print(report_path)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
