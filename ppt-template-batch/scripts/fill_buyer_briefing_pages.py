from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from pptx import Presentation


DEFAULT_MAPPING: dict[str, Any] = {
    "title_shape": 5,
    "buyers_per_slide": 6,
    "slots": [
        {"summary_shape": 15, "products_shape": 23},
        {"summary_group": 16, "summary_child": 2, "products_group": 16, "products_child": 3},
        {"summary_group": 17, "summary_child": 2, "products_group": 17, "products_child": 3},
        {"summary_shape": 19, "products_shape": 26},
        {"summary_shape": 20, "products_shape": 25},
        {"summary_shape": 22, "products_shape": 24},
    ],
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ensure_runs(paragraph, minimum: int) -> None:
    while len(paragraph.runs) < minimum:
        paragraph.add_run()


def get_text_frame(slide, shape_index: int, child_index: int | None = None):
    shape = slide.shapes[shape_index - 1]
    if child_index is not None:
        shape = shape.shapes[child_index - 1]
    return shape.text_frame


def set_single_run_text(text_frame, value: str) -> None:
    paragraph = text_frame.paragraphs[0]
    ensure_runs(paragraph, 1)
    paragraph.runs[0].text = value
    for run in paragraph.runs[1:]:
        run.text = ""


def split_summary(name: str, summary: str) -> tuple[str, str]:
    if summary.startswith(name):
        return name, summary[len(name) :]
    return name, summary


def set_summary_text(text_frame, buyer: dict[str, Any]) -> None:
    name = str(buyer.get("name", "") or "")
    summary = str(buyer.get("summary") or buyer.get("intro") or "")
    paragraph = text_frame.paragraphs[0]
    ensure_runs(paragraph, 2)
    name_text, body_text = split_summary(name, summary)
    paragraph.runs[0].text = name_text
    paragraph.runs[1].text = body_text
    for run in paragraph.runs[2:]:
        run.text = ""


def products_text(buyer: dict[str, Any]) -> str:
    value = str(buyer.get("products") or buyer.get("categories") or "").strip()
    if value.startswith("采购品类："):
        return value
    return f"采购品类：{value}" if value else ""


def fill_slot(slide, slot: dict[str, Any], buyer: dict[str, Any]) -> None:
    if "summary_group" in slot:
        summary_frame = get_text_frame(slide, int(slot["summary_group"]), int(slot["summary_child"]))
    else:
        summary_frame = get_text_frame(slide, int(slot["summary_shape"]))
    set_summary_text(summary_frame, buyer)

    if "products_group" in slot:
        products_frame = get_text_frame(slide, int(slot["products_group"]), int(slot["products_child"]))
    else:
        products_frame = get_text_frame(slide, int(slot["products_shape"]))
    set_single_run_text(products_frame, products_text(buyer))


def fill_slide(slide, page: dict[str, Any], mapping: dict[str, Any]) -> None:
    buyers = page["buyers"]
    buyers_per_slide = int(mapping.get("buyers_per_slide", len(mapping["slots"])))
    if len(buyers) != buyers_per_slide:
        raise ValueError(f"Each briefing slide must contain exactly {buyers_per_slide} buyers.")

    title_frame = get_text_frame(slide, int(mapping["title_shape"]))
    set_single_run_text(title_frame, str(page["title"]))

    for slot, buyer in zip(mapping["slots"], buyers):
        fill_slot(slide, slot, buyer)


def duplicate_slide(presentation: Presentation, source_index: int):
    source_slide = presentation.slides[source_index]
    blank_layout = presentation.slide_layouts[6]
    new_slide = presentation.slides.add_slide(blank_layout)
    for shape in source_slide.shapes:
        new_slide.shapes._spTree.insert_element_before(copy.deepcopy(shape.element), "p:extLst")
    for rel in source_slide.part.rels.values():
        if "notesSlide" in rel.reltype:
            continue
        if rel.rId in new_slide.part.rels:
            continue
        try:
            new_slide.part.rels.add_relationship(rel.reltype, rel._target, rel.rId)
        except Exception:
            pass
    return new_slide


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fill buyer-briefing PPT pages while preserving template run-level text styles."
    )
    parser.add_argument("template", help="Template PPTX path")
    parser.add_argument("pages_json", help="JSON with pages: title + 6 buyers per page")
    parser.add_argument("output", help="Output PPTX path")
    parser.add_argument("--layout-config", help="Optional briefing layout mapping JSON")
    parser.add_argument("--report", help="Optional export report JSON path")
    args = parser.parse_args()

    pages = load_json(Path(args.pages_json))
    mapping = DEFAULT_MAPPING
    if args.layout_config:
        mapping = load_json(Path(args.layout_config))

    prs = Presentation(args.template)
    while len(pages) > len(prs.slides):
        duplicate_slide(prs, len(prs.slides) - 1)

    for index, page in enumerate(pages):
        fill_slide(prs.slides[index], page, mapping)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(output_path)
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps({
            "ok": True,
            "pipeline_mode": "buyer_briefing",
            "page_count": len(pages),
            "output": str(output_path),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
