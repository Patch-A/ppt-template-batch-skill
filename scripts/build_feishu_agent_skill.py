from __future__ import annotations

import argparse
import shutil
import tempfile
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "feishu-agent-skill"
ENGINE_ROOT = REPO_ROOT / "ppt-template-batch"
TOP_LEVEL_SCRIPTS = REPO_ROOT / "scripts"


def ignored(relative: Path) -> bool:
    parts = set(relative.parts)
    if "__pycache__" in parts or ".git" in parts:
        return True
    if parts.intersection({"output", "outputs", "console-projects", "examples", "saudi-three-buyer-boards"}):
        return True
    if relative.as_posix().startswith("assets/examples/"):
        return True
    if relative.as_posix() == "references/sa-example-data.md":
        return True
    return False


def copy_filtered(source: Path, destination: Path) -> int:
    count = 0
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        if ignored(relative):
            continue
        target = destination / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            count += 1
    return count


def build(output: Path) -> Path:
    if not PACKAGE_ROOT.is_dir() or not ENGINE_ROOT.is_dir():
        raise FileNotFoundError("feishu-agent-skill or ppt-template-batch directory is missing.")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ppt-agent-skill-") as temp_dir:
        staging = Path(temp_dir) / "ppt-template-batch-agent-skill"
        staging.mkdir()
        package_files = copy_filtered(PACKAGE_ROOT, staging)
        engine = staging / "engine"
        engine_files = copy_filtered(ENGINE_ROOT, engine / "ppt-template-batch")
        wrapper_files = copy_filtered(TOP_LEVEL_SCRIPTS, engine / "scripts")
        requirements = REPO_ROOT / "requirements.txt"
        if requirements.is_file():
            shutil.copy2(requirements, engine / "requirements.txt")
        manifest = staging / "manifest.json"
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace(
                '\"runtime\": \"agent\"',
                '\"runtime\": \"agent\", \"engine_root\": \"engine\"',
            ),
            encoding="utf-8",
        )
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in staging.rglob("*"):
                if item.is_file():
                    archive.write(item, Path(staging.name) / item.relative_to(staging))
        print(f"Packaged {package_files + engine_files + wrapper_files} files: {output}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the portable Feishu/Aily PPT agent skill ZIP.")
    parser.add_argument("--output", default="output/ppt-template-batch-agent-skill.zip")
    args = parser.parse_args()
    build(Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
