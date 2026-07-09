from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import subprocess
import sys
from pathlib import Path

from env_utils import get_env_var


def check_module(name: str) -> dict[str, object]:
    return {"name": name, "ok": importlib.util.find_spec(name) is not None}


def check_url(url: str) -> dict[str, object]:
    try:
        from fetch_buyer_assets import fetch_url

        final_url, body, content_type = fetch_url(url, timeout=15)
        return {
            "url": url,
            "ok": True,
            "final_url": final_url,
            "content_type": content_type,
            "bytes": len(body),
        }
    except Exception as exc:
        return {"url": url, "ok": False, "error": f"{exc.__class__.__name__}: {exc}"}


def check_powerpoint_com() -> dict[str, object]:
    if platform.system().lower() != "windows":
        return {"ok": False, "reason": "not_windows"}
    command = (
        "$ErrorActionPreference='Stop'; "
        "$pp = New-Object -ComObject PowerPoint.Application; "
        "$pp.Quit(); "
        "'ok'"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}


def check_playwright_runtime() -> dict[str, object]:
    if importlib.util.find_spec("playwright") is None:
        return {"ok": False, "reason": "module_missing"}
    command = [
        sys.executable,
        "-c",
        (
            "from playwright.sync_api import sync_playwright; "
            "p=sync_playwright().start(); "
            "b=p.chromium.launch(headless=True); "
            "page=b.new_page(); "
            "page.goto('https://example.com', wait_until='domcontentloaded', timeout=10000); "
            "print(page.title()); "
            "b.close(); "
            "p.stop()"
        ),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=25,
        )
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}


def build_report() -> dict[str, object]:
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "openai_api_key_visible": bool(get_env_var("OPENAI_API_KEY")),
        "buyer_research_model": get_env_var("BUYER_RESEARCH_MODEL") or "gpt-4.1",
        "curl_fallback_enabled": bool(get_env_var("BUYER_BOARD_ENABLE_CURL_FALLBACK")),
        "modules": [check_module(name) for name in ("openai", "pptx", "PIL", "cairosvg", "playwright")],
        "network": [
            check_url("https://www.scatec.com"),
            check_url("https://html.duckduckgo.com/html/?q=scatec"),
        ],
        "playwright_runtime": check_playwright_runtime(),
        "powerpoint_com": check_powerpoint_com(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check ppt-template-batch runtime readiness.")
    parser.add_argument("--output", default="ppt-template-batch-doctor-report.json", help="Diagnostic report path")
    args = parser.parse_args()

    report = build_report()
    output = Path(args.output).resolve()
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    print(output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

