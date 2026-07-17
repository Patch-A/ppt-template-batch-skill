import json
import importlib
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

class PresetContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fill_buyer_briefing_pages = importlib.import_module("fill_buyer_briefing_pages")
        cls.fill_ppt_from_records = importlib.import_module("fill_ppt_from_records")

        builder_path = REPO_ROOT / "scripts" / "build_feishu_agent_skill.py"
        builder_spec = importlib.util.spec_from_file_location("build_feishu_agent_skill", builder_path)
        if not builder_spec or not builder_spec.loader:
            raise ImportError(f"Unable to load {builder_path}")
        cls.build_feishu_agent_skill = importlib.util.module_from_spec(builder_spec)
        builder_spec.loader.exec_module(cls.build_feishu_agent_skill)

        yitu_path = REPO_ROOT / "yitu-quanjie" / "scripts" / "yitu_quanjie_replace.py"
        yitu_spec = importlib.util.spec_from_file_location("yitu_quanjie_replace", yitu_path)
        if not yitu_spec or not yitu_spec.loader:
            raise ImportError(f"Unable to load {yitu_path}")
        cls.yitu_quanjie_replace = importlib.util.module_from_spec(yitu_spec)
        yitu_spec.loader.exec_module(cls.yitu_quanjie_replace)

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

            report = self.fill_ppt_from_records.fill_presentation(template, records, config, output, root / "workspace")

            self.assertIs(type(report["ok"]), bool)
            self.assertIs(report["ok"], True)
            self.assertIsInstance(report["missing_required_fields"], list)
            self.assertEqual(report["missing_required_fields"], [])
            self.assertIsInstance(report["missing_assets"], list)
            self.assertEqual(report["missing_assets"], [])
            self.assertIsInstance(report["warnings"], list)
            self.assertEqual(report["warnings"], [])

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
            self.fill_buyer_briefing_pages.fill_slide(slide, page, mapping)

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
                self.yitu_quanjie_replace.run_replacement(
                    template_path,
                    output_path,
                    {"Missing Shape": "replacement"},
                )

            self.assertFalse(output_path.exists())

    def test_feishu_zip_contains_only_portable_skill_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = self.build_feishu_agent_skill.build(Path(temp_dir) / "skill.zip")

            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()

            self.assertIn("SKILL.md", names)
            self.assertTrue(names)
            self.assertTrue(all(name == "SKILL.md" or name.startswith("references/") for name in names))
