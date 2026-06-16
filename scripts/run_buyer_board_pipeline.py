from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_skill_root(repo_root: Path) -> Path:
    return repo_root / "buyer-board-layout"


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


def copy_assets_to_workspace(buyers_path: Path, workspace_dir: Path) -> Path:
    workspace_dir.mkdir(parents=True, exist_ok=True)
    copied_buyers = workspace_dir / "buyer-board-buyers.json"

    buyers = json.loads(buyers_path.read_text(encoding="utf-8"))
    for item in buyers:
        for key in ("logo_path", "site_image_path"):
            asset_path = item.get(key)
            if not asset_path:
                continue
            source = (buyers_path.parent / asset_path).resolve()
            destination = (workspace_dir / Path(asset_path).name).resolve()
            shutil.copy2(source, destination)
            item[key] = str(destination)

    copied_buyers.write_text(json.dumps(buyers, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    return copied_buyers


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the buyer-board PPT pipeline end-to-end.")
    parser.add_argument("--template", required=True, help="Template PPTX path")
    parser.add_argument("--buyers", required=True, help="Buyers JSON path")
    parser.add_argument("--layout-config", "--config", dest="layout_config", required=True, help="Layout config JSON path")
    parser.add_argument("--output", required=True, help="Final PPTX output path")
    parser.add_argument("--preview-dir", required=True, help="PNG preview output directory")
    parser.add_argument("--workspace", required=True, help="Temporary workspace directory")
    parser.add_argument("--cover-title", help="Optional cover title override")
    parser.add_argument("--cover-country", help="Optional cover country override")
    parser.add_argument("--content-title", help="Optional content title override")
    args = parser.parse_args()

    repo_root = resolve_repo_root()
    skill_root = resolve_skill_root(repo_root)
    workspace = Path(args.workspace)
    text_draft = workspace / "text-draft.pptx"
    copied_buyers = copy_assets_to_workspace(Path(args.buyers), workspace)

    text_cmd = [
        sys.executable,
        str(skill_root / "scripts" / "fill_buyer_board_text.py"),
        args.template,
        str(copied_buyers),
        args.layout_config,
        str(text_draft),
    ]
    if args.cover_title:
        text_cmd.extend(["--cover-title", args.cover_title])
    if args.cover_country:
        text_cmd.extend(["--cover-country", args.cover_country])
    if args.content_title:
        text_cmd.extend(["--content-title", args.content_title])
    run(text_cmd)

    run(
        [
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
            args.layout_config,
            "-OutputPpt",
            args.output,
            "-PreviewDir",
            args.preview_dir,
        ]
    )

    print(args.output)
    print(args.preview_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
