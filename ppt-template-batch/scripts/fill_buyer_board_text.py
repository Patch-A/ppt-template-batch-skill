from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def get_shape(slide, shape_index: int):
    return slide.shapes[shape_index - 1]


def get_first_run(paragraph):
    if paragraph.runs:
        return paragraph.runs[0]
    return None


def copy_font(source_run, target_run) -> None:
    if source_run is None:
        return

    target_run.font.name = source_run.font.name
    target_run.font.size = source_run.font.size
    target_run.font.bold = source_run.font.bold
    target_run.font.italic = source_run.font.italic
    target_run.font.underline = source_run.font.underline

    try:
        target_run.font.color.rgb = source_run.font.color.rgb
    except Exception:
        try:
            target_run.font.color.theme_color = source_run.font.color.theme_color
        except Exception:
            pass


def replace_text(text_frame, value: str) -> None:
    source_paragraph = text_frame.paragraphs[0]
    source_run = get_first_run(source_paragraph)
    alignment = source_paragraph.alignment

    text_frame.clear()
    paragraph = text_frame.paragraphs[0]
    paragraph.alignment = alignment
    run = paragraph.add_run()
    run.text = value
    copy_font(source_run, run)


def set_shape_text(slide, shape_index: int, value: str) -> None:
    shape = get_shape(slide, shape_index)
    replace_text(shape.text_frame, value)


def set_table_cell(table, row: int, col: int, value: str) -> None:
    cell = table.cell(row, col)
    replace_text(cell.text_frame, value)


def apply_override_color(shape_or_cell, rgb_hex: str) -> None:
    text_frame = shape_or_cell.text_frame
    for paragraph in text_frame.paragraphs:
        for run in paragraph.runs:
            run.font.color.rgb = RGBColor.from_string(rgb_hex)


def fill_cover(presentation: Presentation, config: dict[str, Any], cover_title: str, cover_country: str) -> None:
    cover_config = config["cover"]
    slide = presentation.slides[cover_config["slide_index"] - 1]
    set_shape_text(slide, cover_config["title_shape_index"], cover_title)
    set_shape_text(slide, cover_config["country_shape_index"], cover_country)


def fill_content_slides(
    presentation: Presentation,
    buyers: list[dict[str, Any]],
    config: dict[str, Any],
    content_title: str,
) -> None:
    content_config = config["content"]
    start_slide_index = content_config["start_slide_index"]
    table_shape_index = content_config["table_shape_index"]
    title_shape_index = content_config["title_shape_index"]
    fields = content_config["fields"]

    available_content_slides = len(presentation.slides) - start_slide_index + 1
    if len(buyers) > available_content_slides:
        raise ValueError(
            f"Template only has {available_content_slides} content slides, but buyers.json contains {len(buyers)} buyers."
        )

    for offset, buyer in enumerate(buyers):
        slide = presentation.slides[start_slide_index - 1 + offset]
        set_shape_text(slide, title_shape_index, content_title)

        table = get_shape(slide, table_shape_index).table
        for field in fields:
            row = int(field["row"])
            label_col = int(field.get("label_column", 0))
            value_col = int(field.get("value_column", 1))
            label = str(field.get("label", ""))
            value_key = field["value_key"]
            value = str(buyer.get(value_key, "") or "")

            if label:
                set_table_cell(table, row, label_col, label)
            set_table_cell(table, row, value_col, value)

            if "label_color" in field:
                apply_override_color(table.cell(row, label_col), field["label_color"])
            if "value_color" in field:
                apply_override_color(table.cell(row, value_col), field["value_color"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill buyer-board text content using buyers.json and layout-config.json.")
    parser.add_argument("template", help="Template PPTX path")
    parser.add_argument("buyers", help="Buyers JSON path")
    parser.add_argument("layout_config", help="Layout config JSON path")
    parser.add_argument("output", help="Output PPTX path")
    parser.add_argument("--cover-title", dest="cover_title", help="Override cover title")
    parser.add_argument("--cover-country", dest="cover_country", help="Override cover country line")
    parser.add_argument("--content-title", dest="content_title", help="Override content-page title")
    args = parser.parse_args()

    buyers = load_json(Path(args.buyers))
    config = load_json(Path(args.layout_config))
    presentation = Presentation(args.template)

    defaults = config.get("defaults", {})
    cover_title = args.cover_title or defaults.get("cover_title", "")
    cover_country = args.cover_country or defaults.get("cover_country", "")
    content_title = args.content_title or defaults.get("content_title", "")

    fill_cover(presentation, config, cover_title, cover_country)
    fill_content_slides(presentation, buyers, config, content_title)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    presentation.save(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
