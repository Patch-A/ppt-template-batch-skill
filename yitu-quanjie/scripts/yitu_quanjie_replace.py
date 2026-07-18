#!/usr/bin/env python3
"""Replace the editable regions of a Yitu Quanjie PPTX template."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from pptx import Presentation
from pptx.util import Inches


MIN_TABLE_ROW_HEIGHT = int(Inches(0.25))
EMU_PER_INCH = 914400


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


def text_capacity(shape: Any) -> int | None:
    original_len = len(getattr(shape, "text", ""))
    if not original_len:
        return None
    return max(original_len, int(original_len * 1.05))


def check_length(shape: Any, new_text: str) -> None:
    capacity = text_capacity(shape)
    if capacity is not None and len(new_text) > capacity:
        raise ValueError(
            f"Replacement for {getattr(shape, 'name', '<unknown>')!r} is too long: "
            f"{len(new_text)} characters vs {capacity} capacity"
        )


def _font_size_pt(text_frame: Any, default: float = 14.0) -> float:
    for paragraph in text_frame.paragraphs:
        for run in paragraph.runs:
            if run.font.size is not None:
                return float(run.font.size.pt)
    return default


def _weighted_text_length(value: str) -> float:
    total = 0.0
    for char in value:
        if char == "\n":
            continue
        if "\u4e00" <= char <= "\u9fff":
            total += 1.0
        elif char.isspace():
            total += 0.3
        else:
            total += 0.55
    return total


def _content_row_height(cell: Any, column_width: int, value: str) -> int:
    font_size = max(_font_size_pt(cell.text_frame), 1.0)
    usable_width = max(
        column_width - int(cell.margin_left or 0) - int(cell.margin_right or 0),
        int(Inches(0.5)),
    )
    chars_per_line = max(8.0, usable_width / EMU_PER_INCH * 72.0 / (font_size * 0.95))
    lines = max(
        1,
        sum(
            max(1, int((_weighted_text_length(line) + chars_per_line - 1) // chars_per_line))
            for line in (str(value or "").splitlines() or [""])
        ),
    )
    height_pt = lines * font_size * 1.25 + (
        int(cell.margin_top or 0) + int(cell.margin_bottom or 0)
    ) / 12700 + 2.0
    return max(MIN_TABLE_ROW_HEIGHT, int(Inches(height_pt / 72.0)))


def _shape_map(slide: Any) -> dict[str, Any]:
    shapes: dict[str, Any] = {}

    def collect(shape: Any) -> None:
        name = str(getattr(shape, "name", "") or "")
        if name and name not in shapes:
            shapes[name] = shape

    walk_shapes(slide.shapes, collect)
    return shapes


def _table_shapes(slide: Any) -> list[Any]:
    tables: list[Any] = []

    def collect(shape: Any) -> None:
        if getattr(shape, "has_table", False):
            tables.append(shape)

    walk_shapes(slide.shapes, collect)
    return tables


def _parse_cell_key(key: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"cell_(\d+)(?:_(\d+))?", key)
    if not match:
        return None
    if match.group(2) is None:
        digits = match.group(1)
        if len(digits) != 2:
            return None
        return int(digits[0]), int(digits[1])
    return int(match.group(1)), int(match.group(2))


def _output_errors(input_path: str | Path, output_path: str | Path) -> list[str]:
    input_target = Path(input_path)
    output_target = Path(output_path)
    errors: list[str] = []
    if output_target.exists() and output_target.is_dir():
        errors.append("Output path is a directory")
    if output_target.exists() and input_target.exists():
        try:
            if output_target.resolve() == input_target.resolve():
                errors.append("Output path must differ from the input template")
        except OSError:
            pass
    if output_target.parent.exists() and not output_target.parent.is_dir():
        errors.append("Output parent path is not a directory")
    return errors


def _validation_report(input_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    return {
        "ok": False,
        "input": {"path": str(input_path), "errors": []},
        "output": {"path": str(output_path), "errors": _output_errors(input_path, output_path)},
        "missing_shapes": [],
        "missing_mapped_shapes": [],
        "shape_errors": [],
        "table_errors": [],
        "overflows": [],
        "table_layout": [],
        "minimum_row_height": MIN_TABLE_ROW_HEIGHT,
        "errors": [],
    }


def validate_replacement(
    input_path: str | Path,
    output_path: str | Path,
    content_map: dict[str, str],
    table_data: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Validate all mappings without changing or saving the template."""
    report = _validation_report(input_path, output_path)
    input_target = Path(input_path)
    if not input_target.is_file():
        report["input"]["errors"].append("Input template does not exist or is not a file")
        report["errors"].extend(report["input"]["errors"])
        report["errors"].extend(report["output"]["errors"])
        return report

    try:
        prs = Presentation(str(input_target))
    except Exception as exc:
        report["input"]["errors"].append(f"Unable to open template: {exc}")
        report["errors"].extend(report["input"]["errors"])
        report["errors"].extend(report["output"]["errors"])
        return report
    if not prs.slides:
        report["input"]["errors"].append("The template has no slides")
        report["errors"].extend(report["input"]["errors"])
        report["errors"].extend(report["output"]["errors"])
        return report

    slide = prs.slides[0]
    shapes = _shape_map(slide)
    for name, new_text in content_map.items():
        shape = shapes.get(name)
        if shape is None:
            report["missing_shapes"].append(name)
            continue
        if not getattr(shape, "has_text_frame", False):
            report["shape_errors"].append({"shape": name, "error": "Shape has no text frame"})
            continue
        capacity = text_capacity(shape)
        if capacity is not None and len(new_text) > capacity:
            report["overflows"].append({
                "target": name,
                "kind": "shape",
                "length": len(new_text),
                "capacity": capacity,
            })

    tables = _table_shapes(slide)
    target_table = tables[0] if table_data and tables else None

    replacement_cells: dict[tuple[int, int], str] = {}
    if table_data:
        for key, new_text in table_data.items():
            coordinate = _parse_cell_key(str(key))
            if coordinate is None:
                report["table_errors"].append({"key": key, "error": "Invalid table coordinate"})
                continue
            if target_table is None:
                report["table_errors"].append({"key": key, "error": "No table on the first slide"})
                continue
            row_index, col_index = coordinate
            table = target_table.table
            if row_index >= len(table.rows) or col_index >= len(table.columns):
                report["table_errors"].append({
                    "key": key,
                    "row": row_index,
                    "col": col_index,
                    "error": "Table coordinate is out of bounds",
                })
                continue
            replacement_cells[(row_index, col_index)] = new_text
            cell = table.cell(row_index, col_index)
            capacity = text_capacity(cell)
            if capacity is not None and len(new_text) > capacity:
                report["overflows"].append({
                    "target": key,
                    "kind": "table_cell",
                    "length": len(new_text),
                    "capacity": capacity,
                })

    target_tables = [target_table] if target_table is not None else []
    for table_index, table_shape in enumerate(target_tables):
        table = table_shape.table
        required_height = 0
        for row_index, row in enumerate(table.rows):
            row_values = [
                replacement_cells.get(
                    (row_index, col_index),
                    table.cell(row_index, col_index).text,
                )
                for col_index in range(len(table.columns))
            ]
            value = "\n".join(value for value in row_values if value)
            width = sum(int(column.width) for column in table.columns)
            row_height = _content_row_height(table.cell(row_index, 0), width, value)
            required_height += row_height
        if required_height > int(table_shape.height):
            report["overflows"].append({
                "target": f"table_{table_index}",
                "kind": "table_height",
                "required_height": required_height,
                "capacity": int(table_shape.height),
            })
        report["table_layout"].append({
            "table": table_index,
            "minimum_row_height": MIN_TABLE_ROW_HEIGHT,
            "required_height": required_height,
        })

    report["missing_mapped_shapes"] = list(report["missing_shapes"])
    report["errors"].extend(report["input"]["errors"])
    report["errors"].extend(report["output"]["errors"])
    report["errors"].extend(report["missing_shapes"])
    report["errors"].extend(item["error"] for item in report["shape_errors"])
    report["errors"].extend(item["error"] for item in report["table_errors"])
    report["errors"].extend(item["target"] for item in report["overflows"])
    report["ok"] = not report["errors"]
    return report


def run_replacement(
    input_path: str | Path,
    output_path: str | Path,
    content_map: dict[str, str],
    table_data: dict[str, str] | None = None,
) -> Path:
    """Fill the first slide while preserving the existing run and table styles."""
    report = validate_replacement(input_path, output_path, content_map, table_data)
    if not report["ok"]:
        if report["missing_shapes"]:
            missing = ", ".join(report["missing_shapes"])
            raise KeyError(f"Mapped shapes were not found on the first slide: {missing}")
        if report["overflows"]:
            overflow = report["overflows"][0]
            if "length" in overflow and "capacity" in overflow:
                raise ValueError(
                    f"Replacement for {overflow['target']!r} is too long: "
                    f"{overflow['length']} characters vs {overflow['capacity']} capacity"
                )
            raise ValueError(
                f"Yitu replacement overflow for {overflow['target']!r}: "
                f"required {overflow.get('required_height')} vs capacity {overflow.get('capacity')}"
            )
        raise ValueError("Yitu replacement validation failed: " + "; ".join(report["errors"]))

    prs = Presentation(str(input_path))
    if not prs.slides:
        raise ValueError("The template has no slides")
    slide = prs.slides[0]
    target_tables = _table_shapes(slide)
    target_table = target_tables[0] if table_data and target_tables else None

    def process(shape: Any) -> None:
        name = getattr(shape, "name", "")
        if name in content_map:
            new_text = content_map[name]
            if "\n" in new_text:
                replace_text_keep_lines(shape, new_text)
            else:
                replace_text(shape, new_text)

    walk_shapes(slide.shapes, process)

    if target_table is not None:
        table = target_table.table
        for key, new_text in table_data.items():
            coordinate = _parse_cell_key(str(key))
            if coordinate is None:
                continue
            row_index, col_index = coordinate
            if row_index < len(table.rows) and col_index < len(table.columns):
                replace_cell(table.cell(row_index, col_index), new_text)
        for row in table.rows:
            row_values = [cell.text for cell in row.cells]
            value = "\n".join(item for item in row_values if item)
            width = sum(int(column.width) for column in table.columns)
            row.height = max(
                MIN_TABLE_ROW_HEIGHT,
                _content_row_height(row.cells[0], width, value),
            )

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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate mappings and print JSON without saving an output",
    )
    args = parser.parse_args()
    content_map = load_json(args.content_map)
    table_data = load_json(args.table_data) if args.table_data else None
    if args.dry_run:
        report = validate_replacement(args.template, args.output, content_map, table_data)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    output = run_replacement(args.template, args.output, content_map, table_data)
    print(f"Created: {output} ({os.path.getsize(output):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
