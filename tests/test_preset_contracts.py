import json
import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from pptx import Presentation


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "ppt-template-batch" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from fill_buyer_briefing_pages import DEFAULT_MAPPING, fill_slide
from fill_ppt_from_records import fill_presentation


_BUILDER_PATH = REPO_ROOT / "scripts" / "build_feishu_agent_skill.py"
_BUILDER_SPEC = importlib.util.spec_from_file_location("build_feishu_agent_skill", _BUILDER_PATH)
assert _BUILDER_SPEC and _BUILDER_SPEC.loader
build_feishu_agent_skill = importlib.util.module_from_spec(_BUILDER_SPEC)
_BUILDER_SPEC.loader.exec_module(build_feishu_agent_skill)

_YITU_PATH = REPO_ROOT / "yitu-quanjie" / "scripts" / "yitu_quanjie_replace.py"
_YITU_SPEC = importlib.util.spec_from_file_location("yitu_quanjie_replace", _YITU_PATH)
assert _YITU_SPEC and _YITU_SPEC.loader
yitu_quanjie_replace = importlib.util.module_from_spec(_YITU_SPEC)
_YITU_SPEC.loader.exec_module(yitu_quanjie_replace)


class PresetContractTests(unittest.TestCase):
    def test_generic_report_contains_shared_quality_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "template.pptx"
            records = root / "records.json"
            config = root / "layout-config.json"
            output = root / "output.pptx"
            Presentation().save(template)
            records.write_text(json.dumps({"records": []}), encoding="utf-8")
            config.write_text(json.dumps({"required_fields": [], "slides": []}), encoding="utf-8")

            report = fill_presentation(template, records, config, output, root / "workspace")

            for key in ("ok", "missing_required_fields", "missing_assets", "warnings"):
                self.assertIn(key, report)

    def test_buyer_briefing_clears_unused_slots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            template = Presentation()
            slide = template.slides.add_slide(template.slide_layouts[6])
            mapping = {
                "title_shape": 1,
                "buyers_per_slide": 6,
                "slots": [],
            }
            for index in range(6):
                summary_shape = slide.shapes.add_textbox(0, 0, 100, 100)
                products_shape = slide.shapes.add_textbox(0, 0, 100, 100)
                summary_shape.text = "stale summary"
                products_shape.text = "stale products"
                mapping["slots"].append({
                    "summary_shape": len(slide.shapes) - 1,
                    "products_shape": len(slide.shapes),
                })
            title_shape = slide.shapes.add_textbox(0, 0, 100, 100)
            title_shape.text = "stale title"
            mapping["title_shape"] = len(slide.shapes)

            page = {
                "title": "Category",
                "buyers": [
                    {"name": f"Buyer {index}", "summary": f"Buyer {index} summary", "products": f"Product {index}"}
                    for index in range(5)
                ] + [{}],
            }
            fill_slide(slide, page, mapping)

            self.assertEqual(slide.shapes[mapping["slots"][0]["summary_shape"] - 1].text, "Buyer 0 summary")
            self.assertEqual(slide.shapes[mapping["slots"][0]["products_shape"] - 1].text, "采购品类：Product 0")
            self.assertEqual(slide.shapes[mapping["slots"][5]["summary_shape"] - 1].text, "")
            self.assertEqual(slide.shapes[mapping["slots"][5]["products_shape"] - 1].text, "")

    def test_yitu_missing_shape_fails_without_writing_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template_path = root / "template.pptx"
            output_path = root / "output.pptx"
            presentation = Presentation()
            slide = presentation.slides.add_slide(presentation.slide_layouts[6])
            shape = slide.shapes.add_textbox(0, 0, 100, 100)
            shape.name = "Known Shape"
            presentation.save(template_path)

            with self.assertRaisesRegex(KeyError, "Mapped shapes were not found"):
                yitu_quanjie_replace.run_replacement(
                    template_path,
                    output_path,
                    {"Missing Shape": "replacement"},
                )

            self.assertFalse(output_path.exists())

    def test_feishu_zip_contains_only_portable_skill_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = build_feishu_agent_skill.build(Path(temp_dir) / "skill.zip")

            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()

            self.assertIn("SKILL.md", names)
            self.assertTrue(names)
            self.assertTrue(all(name == "SKILL.md" or name.startswith("references/") for name in names))
