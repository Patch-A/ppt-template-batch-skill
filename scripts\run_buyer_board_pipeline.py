from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_skill_root(repo_root: Path) -> Path:
    return repo_root / "ppt-template-batch"


def decode_output(data: bytes | None) -> str:
    if not data:
        return ""
    for encoding in ("utf-8", "gbk", sys.getdefaultencoding()):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=False)
    stdout = decode_output(result.stdout)
    stderr = decode_output(result.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}")


def write_failure_report(workspace: Path, stage: str, exc: Exception) -> None:
    payload = {
        "stage": stage,
        "error_type": exc.__class__.__name__,
        "error": str(exc),
    }
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "pipeline_failure.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def default_cover_title(args: argparse.Namespace) -> str:
    if args.cover_title:
        return args.cover_title
    if args.country and args.procurement_need:
        return f"{args.country}{args.procurement_need}买家"
    return f"{args.country}买家"


def default_cover_country(args: argparse.Namespace) -> str | None:
    if args.cover_country:
        return args.cover_country
    if args.country:
        return f"国家：{args.country}"
    return None


def default_content_title(args: argparse.Namespace) -> str | None:
    if args.content_title:
        return args.content_title
    if args.country and args.procurement_need:
        return f"{args.country}{args.procurement_need}买家"
    if args.country:
        return f"{args.country}买家需求"
    return None


def ensure_layout_config(args: argparse.Namespace, skill_root: Path, workspace: Path) -> str:
    if args.layout_config:
        return args.layout_config
    if not args.country:
        raise ValueError("Auto-generated layout-config defaults require --country when --layout-config is omitted.")

    generated = workspace / "layout-config.generated.json"
    cmd = [
        sys.executable,
        str(skill_root / "scripts" / "generate_layout_config.py"),
        "--template",
        args.template,
        "--output",
        str(generated),
        "--cover-title",
        default_cover_title(args),
        "--cover-country",
        default_cover_country(args) or "",
        "--content-title",
        default_content_title(args) or "",
    ]
    run(cmd)
    return str(generated)


def generate_buyers_from_research(args: argparse.Namespace, skill_root: Path, workspace: Path) -> Path:
    output_json = workspace / "buyers.generated.json"
    research_dir = workspace / "research"
    cmd = [
        sys.executable,
        str(skill_root / "scripts" / "discover_buyer_profiles.py"),
        "--country",
        args.country,
        "--procurement-need",
        args.procurement_need,
        "--output",
        str(output_json),
        "--workspace",
        str(research_dir),
    ]
    if args.buyer_count:
        cmd.extend(["--buyer-count", str(args.buyer_count)])
    if args.openai_model:
        cmd.extend(["--model", args.openai_model])
    run(cmd)
    return output_json


def enrich_buyer_assets(
    skill_root: Path,
    buyers_path: Path,
    workspace: Path,
    enable_ai_visual_fallback: bool,
    asset_mode: str,
    browser_timeout_ms: int,
) -> Path:
    output_json = workspace / "buyers.with-assets.json"
    assets_dir = workspace / "assets"
    cache_file = workspace / "asset-cache.json"
    report_file = workspace / "asset_fetch_report.json"
    cmd = [
        sys.executable,
        str(skill_root / "scripts" / "fetch_buyer_assets.py"),
        "--buyers",
        str(buyers_path),
        "--output",
        str(output_json),
        "--assets-dir",
        str(assets_dir),
        "--cache-file",
        str(cache_file),
        "--report-file",
        str(report_file),
    ]
    if enable_ai_visual_fallback:
        cmd.append("--enable-ai-visual-fallback")
    if asset_mode:
        cmd.extend(["--asset-mode", asset_mode])
    if browser_timeout_ms:
        cmd.extend(["--browser-timeout-ms", str(browser_timeout_ms)])
    try:
        run(cmd)
        return output_json
    except RuntimeError:
        return buyers_path


def copy_assets_to_workspace(buyers_path: Path, workspace_dir: Path) -> Path:
    workspace_dir.mkdir(parents=True, exist_ok=True)
    copied_buyers = workspace_dir / "buyer-board-buyers.json"

    buyers = load_json(buyers_path)
    for item in buyers:
        for key in ("logo_path", "site_image_path"):
            asset_path = item.get(key)
            if not asset_path:
                continue
            source = (buyers_path.parent / asset_path).resolve() if not Path(asset_path).is_absolute() else Path(asset_path)
            if not source.exists():
                item[key] = ""
                continue
            destination = (workspace_dir / Path(asset_path).name).resolve()
            shutil.copy2(source, destination)
            item[key] = str(destination)

    copied_buyers.write_text(json.dumps(buyers, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    return copied_buyers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the buyer-board PPT pipeline end-to-end.")
    parser.add_argument("--template", required=True, help="Template PPTX path")
    parser.add_argument("--buyers", help="Prepared buyers JSON path")
    parser.add_argument("--layout-config", "--config", dest="layout_config", help="Layout config JSON path")
    parser.add_argument("--output", required=True, help="Final PPTX output path")
    parser.add_argument("--preview-dir", required=True, help="PNG preview output directory")
    parser.add_argument("--workspace", required=True, help="Temporary workspace directory")
    parser.add_argument("--country", help="Country used for auto research mode")
    parser.add_argument("--procurement-need", help="Procurement demand or product direction used for auto research mode")
    parser.add_argument("--buyer-count", type=int, default=5, help="Number of buyers to research in auto mode")
    parser.add_argument("--cover-title", help="Optional cover title override")
    parser.add_argument("--cover-country", help="Optional cover country override")
    parser.add_argument("--content-title", help="Optional content title override")
    parser.add_argument("--openai-model", help="Optional OpenAI model override for research mode")
    parser.add_argument(
        "--asset-mode",
        choices=("light", "auto", "browser"),
        default="light",
        help="Asset fetch mode: light for HTML-only, auto for HTML plus Playwright fallback, browser for Playwright-first fetching",
    )
    parser.add_argument(
        "--browser-timeout-ms",
        type=int,
        default=18000,
        help="Per-page Playwright timeout in milliseconds for browser-enhanced asset fetch modes",
    )
    parser.add_argument(
        "--enable-ai-visual-fallback",
        action="store_true",
        help="Generate AI right-side visuals when public assets are unavailable",
    )
    args = parser.parse_args()

    auto_mode = bool(args.country and args.procurement_need)
    if args.buyers and auto_mode:
        parser.error("Use either --buyers or auto mode (--country + --procurement-need), not both at the same time.")
    if not args.buyers and not auto_mode:
        parser.error("Provide either --buyers or both --country and --procurement-need.")
    if args.buyers and not args.layout_config:
        parser.error("When using --buyers mode, you must also provide --layout-config.")
    return args


def main() -> int:
    args = parse_args()
    repo_root = resolve_repo_root()
    skill_root = resolve_skill_root(repo_root)
    workspace = Path(args.workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    try:
        buyers_path = Path(args.buyers) if args.buyers else generate_buyers_from_research(args, skill_root, workspace)
    except Exception as exc:
        write_failure_report(workspace, "buyer_research", exc)
        print(f"Buyer research failed. See: {workspace / 'pipeline_failure.json'}", file=sys.stderr)
        print(str(exc).split("STDERR:")[-1].strip() or str(exc), file=sys.stderr)
        return 2
    if not args.buyers:
        buyers_path = enrich_buyer_assets(
            skill_root,
            buyers_path,
            workspace,
            args.enable_ai_visual_fallback,
            args.asset_mode,
            args.browser_timeout_ms,
        )
    layout_config = ensure_layout_config(args, skill_root, workspace)
    text_draft = workspace / "text-draft.pptx"
    copied_buyers = copy_assets_to_workspace(buyers_path, workspace)

    country_label = default_cover_country(args)
    content_title = default_content_title(args)

    text_cmd = [
        sys.executable,
        str(skill_root / "scripts" / "fill_buyer_board_text.py"),
        args.template,
        str(copied_buyers),
        layout_config,
        str(text_draft),
    ]
    if args.cover_title:
        text_cmd.extend(["--cover-title", args.cover_title])
    if country_label:
        text_cmd.extend(["--cover-country", country_label])
    if content_title:
        text_cmd.extend(["--content-title", content_title])
    run(text_cmd)

    image_cmd = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(skill_root / "scripts" / "apply_buyer_board_images.ps1"),
        "-InputPpt",
        str(text_draft),
        "-BuyersJson",
        str(copied_buyers),
        "-LayoutConfigJson",
        layout_config,
        "-OutputPpt",
        args.output,
        "-PreviewDir",
        args.preview_dir,
    ]
    try:
        run(image_cmd)
    except RuntimeError as exc:
        message = str(exc)
        if "REGDB_E_CLASSNOTREG" not in message and "NoCOMClassIdentified" not in message:
            raise
        run(
            [
                sys.executable,
                str(skill_root / "scripts" / "apply_buyer_board_images_fallback.py"),
                "--input-ppt",
                str(text_draft),
                "--buyers-json",
                str(copied_buyers),
                "--layout-config",
                layout_config,
                "--output-ppt",
                args.output,
                "--preview-dir",
                args.preview_dir,
            ]
        )

    print(args.output)
    print(args.preview_dir)
    print(copied_buyers)
    print(layout_config)
    report_path = workspace / "asset_fetch_report.json"
    if report_path.exists():
        print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

