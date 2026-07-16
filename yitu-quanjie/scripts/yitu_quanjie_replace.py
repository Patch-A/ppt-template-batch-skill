#!/usr/bin/env python3
"""Replace the editable regions of a Yitu Quanjie PPTX template."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Callable

from pptx import Presentation
from pptx.util import Emu


def clear_runs(text_frame: Any) -> None:
    for paragraph in text_frame.paragraphs:
        for run in paragraph.runs:
            run.text = ""


def set_first_run(paragraph: Any, text: str) -> None:
    if paragraph.runs:
        paragraph.runs[0].text = text
    else:
        paragraph.add_run().text = text


def replace_text(shape: Any, new_text: str) -> None:
    if not getattr(shape, "has_text_frame", False):
        raise TypeError(f"Shape {getattr(shape, 'name', '<unknown>')} has no text frame")
    clear_runs(shape.text_frame)
    set_first_run(shape.text_frame.paragraphs[0], new_text)


def replace_text_keep_lines(shape: Any, new_text: str) -> None:
    if not getattr(shape, "has_text_frame", False):
        raise TypeError(f"Shape {getattr(shape, 'name', '<unknown>')} has no text frame")
    text_frame = shape.text_frame
    clear_runs(text_frame)
    lines = new_text.split("\n")
    paragraphs = list(text_frame.paragraphs)
    while len(paragraphs) < len(lines):
        paragraphs.append(text_frame.add_paragraph())
    for index, paragraph in enumerate(paragraphs):
        set_first_run(paragraph, lines[index] if index < len(lines) else "")


def replace_cell(cell: Any, new_text: str) -> None:
    clear_runs(cell.text_frame)
    set_first_run(cell.text_frame.paragraphs[0], new_text)


def walk_shapes(shapes: Any, callback: Callable[[Any], None]) -> None:
    for shape in shapes:
        callback(shape)
        if getattr(shape, "shape_type", None) == 6:  # GROUP
            walk_shapes(shape.shapes, callback)


def check_length(shape: Any, new_text: str) -> None:
    original_len = len(getattr(shape, "text", ""))
    if original_len and len(new_text) > original_len * 1.05:
        raise ValueError(
            f"Replacement for {shape.name!r} is too long: "
            f"{len(new_text)} characters vs {original_len} in the template"
        )


def run_replacement(
    input_path: str | Path,
    output_path: str | Path,
    content_map: dict[str, str],
    table_data: dict[str, str] | None = None,
) -> Path:
    """Fill the first slide while preserving the existing run and table styles."""
    prs = Presentation(str(input_path))
    if not prs.slides:
        raise ValueError("The template has no slides")
    slide = prs.slides[0]
    replaced = set()

    def process(shape: Any) -> None:
        name = getattr(shape, "name", "")
        if name in content_map:
            new_text = content_map[name]
            check_length(shape, new_text)
            if "\n" in new_text:
                replace_text_keep_lines(shape, new_text)
            else:
                replace_text(shape, new_text)
            replaced.add(name)

        if table_data and getattr(shape, "has_table", False):
            table = shape.table
            keys = ((0, 0, "cell_00"), (0, 1, "cell_01"), (1, 0, "cell_10"), (1, 1, "cell_11"))
            for row_index, col_index, key in keys:
                if key in table_data:
                    replace_cell(table.cell(row_index, col_index), table_data[key])
            for row in table.rows:
                row.height = Emu(0)

    walk_shapes(slide.shapes, process)
    missing = sorted(set(content_map) - replaced)
    if missing:
        raise KeyError(f"Mapped shapes were not found on the first slide: {', '.join(missing)}")

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(target))
    return target


def load_json(path: str | Path) -> dict[str, str]:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return {str(key): str(item) for key, item in value.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill a Yitu Quanjie PPTX template.")
    parser.add_argument("--template", required=True, help="Input PPTX template")
    parser.add_argument("--output", required=True, help="Output PPTX path")
    parser.add_argument("--content-map", required=True, help="JSON object mapping shape names to text")
    parser.add_argument("--table-data", help="Optional JSON object for cell_00/cell_01/cell_10/cell_11")
    args = parser.parse_args()
    output = run_replacement(
        args.template,
        args.output,
        load_json(args.content_map),
        load_json(args.table_data) if args.table_data else None,
    )
    print(f"Created: {output} ({os.path.getsize(output):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
