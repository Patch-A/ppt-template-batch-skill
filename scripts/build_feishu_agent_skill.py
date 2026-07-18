from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "feishu-agent-skill"
INPUT_SCHEMA_PATH = Path("references/input-schema.json")
EXPECTED_CONTRACT_VERSION = "1.0"
REQUIRED_FILES = (
    Path("SKILL.md"),
    Path("references/agent-runtime.md"),
    INPUT_SCHEMA_PATH,
)


def validate_input_schema(package_root: Path) -> None:
    schema_path = package_root / INPUT_SCHEMA_PATH
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON in {INPUT_SCHEMA_PATH.as_posix()}") from exc

    properties = schema.get("properties") if isinstance(schema, dict) else None
    contract_schema = properties.get("contract_version") if isinstance(properties, dict) else None
    if not isinstance(contract_schema, dict) or contract_schema.get("default") != EXPECTED_CONTRACT_VERSION:
        raise ValueError(
            f'Invalid contract_version in {INPUT_SCHEMA_PATH.as_posix()}: '
            f'expected "{EXPECTED_CONTRACT_VERSION}"'
        )


def validate_package(source: Path) -> list[Path]:
    if source.is_symlink():
        raise ValueError(f"Symlink package roots are not allowed: {source}")
    package_root = source.resolve()
    missing = [relative.as_posix() for relative in REQUIRED_FILES if not (package_root / relative).is_file()]
    if missing:
        raise ValueError(f"Missing required package files: {', '.join(missing)}")

    entries = sorted(package_root.rglob("*"), key=lambda item: item.as_posix())
    unsupported: list[str] = []
    files: list[Path] = []
    for item in entries:
        if item.is_symlink():
            raise ValueError(f"Symlinks are not allowed in package: {item}")
        resolved = item.resolve()
        try:
            resolved.relative_to(package_root)
        except ValueError as exc:
            raise ValueError(f"Package path escapes package root: {item}") from exc

        relative = item.relative_to(package_root)
        is_reference_path = relative.parts and relative.parts[0] == "references"
        is_allowed = relative == Path("SKILL.md") or is_reference_path
        if not is_allowed:
            unsupported.append(relative.as_posix())
        elif item.is_file():
            files.append(item)

    if unsupported:
        raise ValueError(f"Unsupported package paths: {', '.join(unsupported)}")
    validate_input_schema(package_root)
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
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=str(output.parent)
    )
    os.close(fd)
    temporary_output = Path(temporary_name)
    try:
        with tempfile.TemporaryDirectory(prefix="ppt-agent-skill-") as temp_dir:
            staging = Path(temp_dir) / "ppt-template-batch-agent-skill"
            staging.mkdir()
            package_files = copy_filtered(PACKAGE_ROOT, staging)
            with zipfile.ZipFile(temporary_output, "w", zipfile.ZIP_DEFLATED) as archive:
                for item in staging.rglob("*"):
                    if item.is_file():
                        archive.write(item, item.relative_to(staging).as_posix())
            with zipfile.ZipFile(temporary_output, "r") as archive:
                invalid_member = archive.testzip()
                if invalid_member is not None:
                    raise ValueError(f"ZIP validation failed: {invalid_member}")
        os.replace(temporary_output, output)
    except Exception:
        try:
            temporary_output.unlink()
        except FileNotFoundError:
            pass
        raise
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
