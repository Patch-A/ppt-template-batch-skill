import json
import importlib
import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from argparse import Namespace
from unittest.mock import patch

from pptx import Presentation
from pptx.util import Inches


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
        cls.generate_layout_config = importlib.import_module("generate_layout_config")

        pipeline_path = REPO_ROOT / "scripts" / "run_ppt_batch_pipeline.py"
        pipeline_spec = importlib.util.spec_from_file_location("run_ppt_batch_pipeline", pipeline_path)
        if not pipeline_spec or not pipeline_spec.loader:
            raise ImportError(f"Unable to load {pipeline_path}")
        cls.run_ppt_batch_pipeline = importlib.util.module_from_spec(pipeline_spec)
        pipeline_spec.loader.exec_module(cls.run_ppt_batch_pipeline)

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
            self.assertEqual(report["schema_version"], 2)
            self.assertIsInstance(report["stale_template_text"], list)
            self.assertIsInstance(report["capacity_warnings"], list)
            self.assertEqual(report["expected_slide_count"], 0)
            self.assertIs(report["reopen_ok"], True)
            self.assertEqual(report["reopen_status"]["status"], "ok")

    def test_generic_selector_precedes_numeric_shape_index(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "template.pptx"
            records = root / "records.json"
            config = root / "layout-config.json"
            output = root / "output.pptx"

            presentation = Presentation()
            slide = presentation.slides.add_slide(presentation.slide_layouts[6])
            numeric_target = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
            numeric_target.name = "Numeric fallback"
            numeric_target.text = "wrong target"
            stable_target = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(3), Inches(1))
            stable_target.name = "Stable title"
            stable_target.text = "template title"
            presentation.save(template)

            records.write_text(json.dumps({"records": [{"name": "Resolved title"}]}), encoding="utf-8")
            config.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "required_fields": ["name"],
                        "slides": [
                            {
                                "slide_index": 1,
                                "record_index": 1,
                                "texts": [
                                    {
                                        "selector": {"name": "Stable title", "role": "text"},
                                        "shape_index": 1,
                                        "field": "name",
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = self.fill_ppt_from_records.fill_presentation(
                template, records, config, output, root / "workspace"
            )

            self.assertIs(report["ok"], True)
            result = Presentation(output)
            self.assertEqual(result.slides[0].shapes[0].text, "wrong target")
            self.assertEqual(result.slides[0].shapes[1].text, "Resolved title")

    def test_selector_role_text_matches_real_placeholder_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "template.pptx"
            records = root / "records.json"
            config = root / "layout-config.json"
            output = root / "output.pptx"

            presentation = Presentation()
            slide = presentation.slides.add_slide(presentation.slide_layouts[1])
            numeric_target = slide.placeholders[0]
            numeric_target.name = "Numeric fallback"
            numeric_target.text = "wrong target"
            placeholder_target = slide.placeholders[1]
            placeholder_target.name = "Real content placeholder"
            placeholder_target.text = "template content"
            presentation.save(template)

            records.write_text(json.dumps({"records": [{"name": "Resolved placeholder"}]}), encoding="utf-8")
            config.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "required_fields": ["name"],
                        "slides": [
                            {
                                "slide_index": 1,
                                "record_index": 1,
                                "texts": [
                                    {
                                        "selector": {
                                            "name": "Real content placeholder",
                                            "role": "text",
                                        },
                                        "shape_index": 1,
                                        "field": "name",
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            self.fill_ppt_from_records.fill_presentation(
                template, records, config, output, root / "workspace"
            )

            result = Presentation(output)
            self.assertEqual(result.slides[0].shapes[0].text, "wrong target")
            self.assertEqual(result.slides[0].shapes[1].text, "Resolved placeholder")

    def test_generated_layout_config_uses_schema_v2_and_stable_selectors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "template.pptx"
            output = root / "layout-config.json"

            presentation = Presentation()
            cover = presentation.slides.add_slide(presentation.slide_layouts[6])
            title = cover.shapes.add_textbox(Inches(1), Inches(0.2), Inches(4), Inches(1))
            title.name = "Cover title"
            title.text = "Title"
            country = cover.shapes.add_textbox(Inches(1), Inches(1.5), Inches(4), Inches(0.5))
            country.name = "Cover country"
            country.text = "Country: Example"
            content = presentation.slides.add_slide(presentation.slide_layouts[6])
            content_title = content.shapes.add_textbox(Inches(1), Inches(0.2), Inches(4), Inches(0.5))
            content_title.name = "Content title"
            content_title.text = "Content"
            table = content.shapes.add_table(2, 2, Inches(1), Inches(2), Inches(4), Inches(2))
            table.name = "Content table"
            presentation.save(template)

            old_argv = sys.argv
            try:
                sys.argv = [
                    "generate_layout_config.py",
                    "--template",
                    str(template),
                    "--output",
                    str(output),
                ]
                self.assertEqual(self.generate_layout_config.main(), 0)
            finally:
                sys.argv = old_argv

            generated = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(generated["schema_version"], 2)
            self.assertEqual(generated["cover"]["title_selector"]["name"], "Cover title")
            self.assertEqual(generated["content"]["table_selector"]["name"], "Content table")

    def test_strict_missing_required_fields_rejects_without_writing_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "template.pptx"
            records = root / "records.json"
            config = root / "layout-config.json"
            output = root / "output.pptx"
            Presentation().save(template)
            records.write_text(json.dumps({"records": [{}]}), encoding="utf-8")
            config.write_text(json.dumps({"required_fields": ["name"], "slides": []}), encoding="utf-8")

            report = self.fill_ppt_from_records.fill_presentation(
                template, records, config, output, root / "workspace", strict=True
            )

            self.assertIs(report["ok"], False)
            self.assertEqual(report["missing_required_fields"], [{"record_index": 1, "field": "name"}])
            self.assertEqual(report["reopen_status"]["status"], "not_run")
            self.assertFalse(output.exists())

    def test_generic_report_identifies_stale_text_and_capacity_warnings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "template.pptx"
            records = root / "records.json"
            config = root / "layout-config.json"
            output = root / "output.pptx"

            presentation = Presentation()
            slide = presentation.slides.add_slide(presentation.slide_layouts[6])
            stale = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
            stale.name = "Unmapped placeholder"
            stale.text = "{{record.name}}"
            overflow = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(0.5), Inches(0.2))
            overflow.name = "Small box"
            overflow.text = "x" * 200
            presentation.save(template)
            records.write_text(json.dumps({"records": []}), encoding="utf-8")
            config.write_text(json.dumps({"schema_version": 2, "slides": []}), encoding="utf-8")

            report = self.fill_ppt_from_records.fill_presentation(
                template, records, config, output, root / "workspace"
            )

            self.assertTrue(report["stale_template_text"])
            self.assertTrue(report["capacity_warnings"])
            self.assertEqual(report["slide_count"], 1)
            self.assertIs(report["reopen_ok"], True)

    def test_pipeline_does_not_reuse_stale_report_after_runner_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            stale_report = root / "fill-report.json"
            stale_report.write_text(
                json.dumps({"ok": True, "record_count": 999}), encoding="utf-8"
            )
            job = {
                "template": str(root / "template.pptx"),
                "records": str(root / "records.json"),
                "layout_config": str(root / "layout-config.json"),
                "output": str(root / "output.pptx"),
                "report": str(stale_report),
            }
            defaults = Namespace(
                template=None,
                records=None,
                layout_config=None,
                output=None,
                output_dir=None,
                workspace=None,
                strict=False,
            )

            with patch.object(
                self.run_ppt_batch_pipeline,
                "run",
                side_effect=RuntimeError("simulated filler failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated filler failure"):
                    self.run_ppt_batch_pipeline.run_single_job(job, defaults, 1)

            self.assertEqual(
                json.loads(stale_report.read_text(encoding="utf-8")),
                {"ok": True, "record_count": 999},
            )

    def test_non_strict_repeat_skips_failed_records_and_reports_them(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "template.pptx"
            records = root / "records.json"
            config = root / "layout-config.json"
            output = root / "output.pptx"

            presentation = Presentation()
            slide = presentation.slides.add_slide(presentation.slide_layouts[6])
            name_shape = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
            name_shape.name = "Record name"
            name_shape.text = "template name"
            presentation.save(template)
            records.write_text(json.dumps({"records": [{"name": "Good"}, {}]}), encoding="utf-8")
            config.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "required_fields": ["name"],
                        "repeat": {
                            "source_slide_index": 1,
                            "start_slide_index": 1,
                            "template_slide_count": 1,
                            "texts": [
                                {
                                    "selector": {"name": "Record name", "role": "text"},
                                    "field": "name",
                                }
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )

            report = self.fill_ppt_from_records.fill_presentation(
                template, records, config, output, root / "workspace"
            )

            self.assertIs(report["ok"], False)
            self.assertEqual(report["failed_records"], [{"record_index": 2, "missing_required_fields": ["name"]}])
            result = Presentation(output)
            self.assertEqual(len(result.slides), 1)
            self.assertEqual(result.slides[0].shapes[0].text, "Good")

    def test_repeat_max_records_truncates_before_filtering_failed_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "template.pptx"
            records = root / "records.json"
            config = root / "layout-config.json"
            output = root / "output.pptx"

            presentation = Presentation()
            slide = presentation.slides.add_slide(presentation.slide_layouts[6])
            name_shape = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
            name_shape.name = "Record name"
            name_shape.text = "template name"
            presentation.save(template)
            records.write_text(
                json.dumps({"records": [{}, {"name": "B"}, {"name": "C"}]}),
                encoding="utf-8",
            )
            config.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "required_fields": ["name"],
                        "repeat": {
                            "source_slide_index": 1,
                            "start_slide_index": 1,
                            "template_slide_count": 1,
                            "max_records": 2,
                            "texts": [
                                {
                                    "selector": {"name": "Record name", "role": "text"},
                                    "field": "name",
                                }
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )

            report = self.fill_ppt_from_records.fill_presentation(
                template, records, config, output, root / "workspace"
            )

            self.assertEqual(report["failed_records"], [{"record_index": 1, "missing_required_fields": ["name"]}])
            result = Presentation(output)
            self.assertEqual(len(result.slides), 1)
            self.assertEqual(result.slides[0].shapes[0].text, "B")

    def test_table_cell_capacity_uses_column_and_row_dimensions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "template.pptx"
            records = root / "records.json"
            config = root / "layout-config.json"
            output = root / "output.pptx"

            presentation = Presentation()
            slide = presentation.slides.add_slide(presentation.slide_layouts[6])
            table_shape = slide.shapes.add_table(
                1, 2, Inches(1), Inches(1), Inches(7), Inches(2)
            )
            table_shape.name = "Wide table"
            table_shape.table.columns[0].width = Inches(0.25)
            table_shape.table.columns[1].width = Inches(6.75)
            table_shape.table.rows[0].height = Inches(2)
            table_shape.table.cell(0, 0).text = "narrow cell " + ("x" * 200)
            presentation.save(template)
            records.write_text(json.dumps({"records": []}), encoding="utf-8")
            config.write_text(json.dumps({"schema_version": 2, "slides": []}), encoding="utf-8")

            report = self.fill_ppt_from_records.fill_presentation(
                template, records, config, output, root / "workspace"
            )

            self.assertTrue(
                any(
                    warning.get("row") == 0 and warning.get("col") == 0
                    for warning in report["capacity_warnings"]
                )
            )

    def test_non_strict_failed_slide_is_cleared_instead_of_preserving_template_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "template.pptx"
            records = root / "records.json"
            config = root / "layout-config.json"
            output = root / "output.pptx"

            presentation = Presentation()
            slide = presentation.slides.add_slide(presentation.slide_layouts[6])
            stale_shape = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
            stale_shape.name = "Failed record content"
            stale_shape.text = "OLD TEMPLATE CONTENT"
            presentation.save(template)
            records.write_text(json.dumps({"records": [{"name": "Good"}, {}]}), encoding="utf-8")
            config.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "required_fields": ["name"],
                        "slides": [
                            {
                                "slide_index": 1,
                                "record_index": 2,
                                "texts": [{"shape_index": 1, "field": "name"}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = self.fill_ppt_from_records.fill_presentation(
                template, records, config, output, root / "workspace"
            )

            self.assertEqual(report["failed_records"], [{"record_index": 2, "missing_required_fields": ["name"]}])
            result = Presentation(output)
            self.assertFalse(any("OLD TEMPLATE CONTENT" in shape.text for shape in result.slides[0].shapes if getattr(shape, "has_text_frame", False)))

    def test_non_strict_pipeline_preserves_failed_record_details_and_continues(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "template.pptx"
            config = root / "layout-config.json"
            bad_records = root / "bad-records.json"
            good_records = root / "good-records.json"
            batch = root / "batch.json"
            report_path = root / "batch-report.json"
            bad_output = root / "bad-output.pptx"
            good_output = root / "good-output.pptx"

            Presentation().save(template)
            config.write_text(json.dumps({"required_fields": ["name"], "slides": []}), encoding="utf-8")
            bad_records.write_text(json.dumps({"records": [{}]}), encoding="utf-8")
            good_records.write_text(json.dumps({"records": [{"name": "Good"}]}), encoding="utf-8")
            batch.write_text(
                json.dumps(
                    [
                        {
                            "template": str(template),
                            "records": str(bad_records),
                            "layout_config": str(config),
                            "output": str(bad_output),
                        },
                        {
                            "template": str(template),
                            "records": str(good_records),
                            "layout_config": str(config),
                            "output": str(good_output),
                        },
                    ]
                ),
                encoding="utf-8",
            )

            old_argv = sys.argv
            try:
                sys.argv = [
                    "run_ppt_batch_pipeline.py",
                    "--batch",
                    str(batch),
                    "--report",
                    str(report_path),
                ]
                self.assertEqual(self.run_ppt_batch_pipeline.main(), 2)
            finally:
                sys.argv = old_argv

            batch_report = json.loads(report_path.read_text(encoding="utf-8-sig"))
            self.assertEqual(len(batch_report["jobs"]), 2)
            self.assertEqual(
                batch_report["jobs"][0]["failed_records"],
                [{"record_index": 1, "missing_required_fields": ["name"]}],
            )
            self.assertIs(batch_report["jobs"][1]["ok"], True)
            self.assertTrue(good_output.exists())

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
