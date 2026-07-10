from __future__ import annotations

import argparse
import csv
import json
import re
import zipfile
from io import StringIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
SUPPORTED_SUFFIXES = {".txt", ".md", ".csv", ".json", ".docx"}


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        document = ElementTree.fromstring(archive.read("word/document.xml"))
    blocks: list[str] = []
    body = document.find("w:body", WORD_NS)
    if body is None:
        return ""
    for child in body:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = "".join(node.text or "" for node in child.findall(".//w:t", WORD_NS)).strip()
            if text:
                blocks.append(text)
        elif tag == "tbl":
            for row in child.findall(".//w:tr", WORD_NS):
                cells = []
                for cell in row.findall("w:tc", WORD_NS):
                    text = "".join(node.text or "" for node in cell.findall(".//w:t", WORD_NS)).strip()
                    cells.append(text)
                if any(cells):
                    blocks.append(" | ".join(cells))
    return "\n".join(blocks)


def load_source(path: Path) -> tuple[str, Any | None]:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"不支持的资料格式：{suffix}。支持 TXT、Markdown、CSV、JSON、DOCX。")
    if suffix == ".json":
        payload = json.loads(read_text(path))
        return json.dumps(payload, ensure_ascii=False, indent=2), payload
    if suffix == ".csv":
        text = read_text(path)
        rows = list(csv.DictReader(StringIO(text)))
        return text, rows
    if suffix == ".docx":
        return read_docx(path), None
    return read_text(path), None


def clean_key(value: str) -> str:
    key = re.sub(r"\s+", "_", value.strip())
    key = re.sub(r"[^\w\u4e00-\u9fff-]+", "", key)
    return key[:80] or "content"


def paragraph_records(text: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n")]
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if not line:
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(line)
    if current:
        blocks.append(current)

    records: list[dict[str, Any]] = []
    heading_re = re.compile(r"^(?:#{1,6}\s+|第[一二三四五六七八九十百0-9]+[章节部分]\s*)?(.{1,80})$")
    for index, block in enumerate(blocks, start=1):
        record: dict[str, Any] = {}
        free_text: list[str] = []
        for line in block:
            match = re.match(r"^([^:：|]{1,40})[:：]\s*(.+)$", line)
            if match:
                record[clean_key(match.group(1))] = match.group(2).strip()
            else:
                free_text.append(line)
        if free_text:
            first = free_text[0].lstrip("#").strip()
            looks_like_heading = bool(heading_re.fullmatch(free_text[0])) and len(first) <= 40
            if looks_like_heading and len(free_text) > 1:
                record.setdefault("title", first)
                record["content"] = "\n".join(free_text[1:])
            else:
                record.setdefault("title", first if len(first) <= 80 else f"记录{index}")
                record["content"] = "\n".join(free_text)
        if record:
            records.append(record)
    if records:
        return records
    stripped = text.strip()
    return [{"title": "导入资料", "content": stripped}] if stripped else []


def normalize_payload(raw_text: str, parsed: Any | None, project_name: str, instruction: str) -> dict[str, Any]:
    if isinstance(parsed, dict) and isinstance(parsed.get("records"), list):
        payload = parsed
        payload.setdefault("globals", {})
    elif isinstance(parsed, list):
        payload = {"globals": {}, "records": [item if isinstance(item, dict) else {"content": str(item)} for item in parsed]}
    elif isinstance(parsed, dict):
        payload = {"globals": {}, "records": [parsed]}
    else:
        payload = {"globals": {}, "records": paragraph_records(raw_text)}
    payload["globals"].setdefault("deck_title", project_name)
    payload["globals"]["source_instruction"] = instruction
    payload["globals"]["source_text"] = raw_text
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Import TXT, Markdown, CSV, JSON, or DOCX into records.json.")
    parser.add_argument("--input", required=True, help="Input document path")
    parser.add_argument("--output", required=True, help="Output records.json path")
    parser.add_argument("--project-name", default="PPT项目")
    parser.add_argument("--instruction", default="", help="Natural-language instructions for later structuring or mapping")
    args = parser.parse_args()

    input_path = Path(args.input)
    raw_text, parsed = load_source(input_path)
    payload = normalize_payload(raw_text, parsed, args.project_name, args.instruction)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
