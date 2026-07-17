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

    def test_buyer_briefing_rejects_more_than_six_buyers_per_page(self):
        page = {"title": "Category", "buyers": [{"name": str(index)} for index in range(7)]}

        with self.assertRaisesRegex(ValueError, "exactly 6 buyers"):
            fill_slide(None, page, DEFAULT_MAPPING)

    @unittest.skip("No public Buyer Briefing API currently exposes unused-slot clearing for direct contract testing.")
    def test_buyer_briefing_clears_unused_slots(self):
        self.fail("Enable when the public briefing export API exposes slot clearing.")

    @unittest.skip("Yitu replacement currently has no public dry-run mode or dry-run report contract.")
    def test_yitu_dry_run_reports_missing_shapes_without_saving(self):
        self.fail("Enable when yitu_quanjie_replace.run_replacement exposes dry_run.")

    def test_feishu_zip_contains_only_portable_skill_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = build_feishu_agent_skill.build(Path(temp_dir) / "skill.zip")

            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()

            self.assertIn("SKILL.md", names)
            self.assertTrue(names)
            self.assertTrue(all(name == "SKILL.md" or name.startswith("references/") for name in names))
