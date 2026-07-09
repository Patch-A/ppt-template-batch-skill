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


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def resolve_buyers_source(workspace: Path, explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Buyers JSON not found: {path}")
        return path
    candidate = first_existing(
        [
            workspace / "buyers.generated.json",
            workspace / "buyers.with-assets.json",
            workspace / "buyer-board-buyers.json",
        ]
    )
    if candidate is None:
        raise FileNotFoundError(
            "Could not find buyers JSON in workspace. Expected one of: "
            "buyers.generated.json, buyers.with-assets.json, buyer-board-buyers.json"
        )
    return candidate.resolve()


def resolve_layout_config(workspace: Path, explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Layout config not found: {path}")
        return path
    candidate = first_existing(
        [
            workspace / "layout-config.generated.json",
            workspace / "layout-config.json",
        ]
    )
    if candidate is None:
        raise FileNotFoundError(
            "Could not find layout-config JSON in workspace. "
            "Pass --layout-config manually or keep layout-config.generated.json."
        )
    return candidate.resolve()


def resolve_input_ppt(workspace: Path, explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Input PPT not found: {path}")
        return path
    candidate = first_existing(
        [
            workspace / "text-draft.pptx",
            workspace / "finished.pptx",
        ]
    )
    if candidate is None:
        raise FileNotFoundError(
            "Could not find an input PPT in workspace. Expected text-draft.pptx or finished.pptx. "
            "Pass --input-ppt manually if your file lives elsewhere."
        )
    return candidate.resolve()


def copy_assets_to_workspace(buyers_path: Path, workspace_dir: Path, output_name: str) -> Path:
    workspace_dir.mkdir(parents=True, exist_ok=True)
    copied_buyers = workspace_dir / output_name

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

    save_json(copied_buyers, buyers)
    return copied_buyers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recover real buyer logo and website visuals locally after a WorkBuddy-sandboxed run."
    )
    parser.add_argument("--workspace", required=True, help="Workspace directory produced by the pipeline or WorkBuddy run")
    parser.add_argument("--buyers-json", help="Optional buyers JSON override")
    parser.add_argument("--layout-config", help="Optional layout-config override")
    parser.add_argument("--input-ppt", help="Optional PPT override, defaults to workspace text-draft.pptx")
    parser.add_argument("--output-ppt", help="Optional recovered PPT output path")
    parser.add_argument("--preview-dir", help="Optional preview output directory")
    parser.add_argument(
        "--asset-mode",
        choices=("light", "auto", "browser"),
        default="auto",
        help="Asset fetch mode for the recovery pass. Use browser for the most aggressive real-site recovery.",
    )
    parser.add_argument(
        "--browser-timeout-ms",
        type=int,
        default=18000,
        help="Per-page timeout for Playwright-enhanced asset recovery",
    )
    parser.add_argument(
        "--enable-ai-visual-fallback",
        action="store_true",
        help="Allow AI right-side visual fallback when no verified public visual is available. Logo is never AI-generated.",
    )
    parser.add_argument(
        "--skip-ppt-refresh",
        action="store_true",
        help="Only regenerate buyers JSON with recovered real assets, without applying them back into a PPT",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = resolve_repo_root()
    skill_root = resolve_skill_root(repo_root)
    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    buyers_source = resolve_buyers_source(workspace, args.buyers_json)
    recovered_buyers = workspace / "buyers.recovered-assets.json"
    assets_dir = workspace / "assets"
    cache_file = workspace / "asset-cache.json"
    report_file = workspace / "asset_fetch_report.json"

    fetch_cmd = [
        sys.executable,
        str(skill_root / "scripts" / "fetch_buyer_assets.py"),
        "--buyers",
        str(buyers_source),
        "--output",
        str(recovered_buyers),
        "--assets-dir",
        str(assets_dir),
        "--cache-file",
        str(cache_file),
        "--report-file",
        str(report_file),
        "--asset-mode",
        args.asset_mode,
        "--browser-timeout-ms",
        str(args.browser_timeout_ms),
    ]
    if args.enable_ai_visual_fallback:
        fetch_cmd.append("--enable-ai-visual-fallback")
    run(fetch_cmd)

    copied_buyers = copy_assets_to_workspace(
        recovered_buyers,
        workspace,
        output_name="buyer-board-buyers.recovered.json",
    )

    print(recovered_buyers)
    print(report_file)
    print(copied_buyers)

    if args.skip_ppt_refresh:
        return 0

    layout_config = resolve_layout_config(workspace, args.layout_config)
    input_ppt = resolve_input_ppt(workspace, args.input_ppt)
    output_ppt = Path(args.output_ppt).resolve() if args.output_ppt else (workspace / "recovered-real-assets.pptx")
    preview_dir = Path(args.preview_dir).resolve() if args.preview_dir else (workspace / "recovered-previews")

    image_cmd = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(skill_root / "scripts" / "apply_buyer_board_images.ps1"),
        "-InputPpt",
        str(input_ppt),
        "-BuyersJson",
        str(copied_buyers),
        "-LayoutConfigJson",
        str(layout_config),
        "-OutputPpt",
        str(output_ppt),
        "-PreviewDir",
        str(preview_dir),
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
                str(input_ppt),
                "--buyers-json",
                str(copied_buyers),
                "--layout-config",
                str(layout_config),
                "--output-ppt",
                str(output_ppt),
                "--preview-dir",
                str(preview_dir),
            ]
        )

    print(output_ppt)
    print(preview_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

