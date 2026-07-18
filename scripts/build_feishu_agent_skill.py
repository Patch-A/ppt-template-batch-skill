from __future__ import annotations

import argparse
import shutil
import tempfile
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "feishu-agent-skill"
REQUIRED_FILES = (
    Path("SKILL.md"),
    Path("references/agent-runtime.md"),
    Path("references/input-schema.json"),
)


def validate_package(source: Path) -> list[Path]:
    missing = [relative.as_posix() for relative in REQUIRED_FILES if not (source / relative).is_file()]
    if missing:
        raise ValueError(f"Missing required package files: {', '.join(missing)}")

    entries = sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix())
    unsupported: list[str] = []
    files: list[Path] = []
    for item in entries:
        relative = item.relative_to(source)
        is_reference_path = relative.parts and relative.parts[0] == "references"
        is_allowed = relative == Path("SKILL.md") or is_reference_path
        if not is_allowed:
            unsupported.append(relative.as_posix())
        elif item.is_file():
            files.append(item)

    if unsupported:
        raise ValueError(f"Unsupported package paths: {', '.join(unsupported)}")
    return files


def copy_filtered(source: Path, destination: Path) -> int:
    count = 0
    for item in validate_package(source):
        relative = item.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        count += 1
    return count


def build(output: Path) -> Path:
    if not PACKAGE_ROOT.is_dir():
        raise FileNotFoundError("feishu-agent-skill directory is missing.")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ppt-agent-skill-") as temp_dir:
        staging = Path(temp_dir) / "ppt-template-batch-agent-skill"
        staging.mkdir()
        package_files = copy_filtered(PACKAGE_ROOT, staging)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in staging.rglob("*"):
                if item.is_file():
                    archive.write(item, item.relative_to(staging).as_posix())
        print(f"Packaged {package_files} Aily-compatible files: {output}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the portable Feishu/Aily PPT agent skill ZIP.")
    parser.add_argument("--output", default="output/ppt-template-batch-agent-skill.zip")
    args = parser.parse_args()
    build(Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
