import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "ppt-template-batch" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from control_console import ConsoleState
from discover_buyer_profiles import normalize_buyers as normalize_cli_buyers
from discover_buyer_profiles import pad_or_trim_bio, refine_buyer_products


class BuyerQualityRegressionTests(unittest.TestCase):
    def test_refine_buyer_products_narrows_copied_global_need(self):
        result = refine_buyer_products(
            "电机、减速机",
            "电机、减速机",
            "输送线仅确认使用电机",
        )

        self.assertEqual(result, "电机")

    def test_bio_padding_does_not_invent_procurement_claims(self):
        result = pad_or_trim_bio("企业位于当地，提供工业产品和技术服务。")

        self.assertNotIn("采购计划稳定", result)
        self.assertNotIn("具备持续采购能力", result)
        self.assertNotIn("设备精度", result)
        self.assertNotIn("交付效率", result)
        self.assertNotIn("长期售后支持", result)

    def test_refine_buyer_products_marks_copied_short_request_without_evidence(self):
        result = refine_buyer_products(
            "电机、减速机",
            "电机、减速机",
            "企业介绍没有列出具体设备。",
        )

        self.assertEqual(result, "需核实具体设备")

    def test_cli_and_console_keep_unverified_product_warnings(self):
        buyer = {
            "name": "示例买家",
            "products": "电机、减速机",
            "bio": "企业位于当地，提供工业产品和技术服务。",
        }
        cli_buyers = normalize_cli_buyers(
            [buyer],
            "中国",
            {"procurement_need": "电机、减速机"},
        )

        with TemporaryDirectory() as temporary_directory:
            console = ConsoleState(Path(temporary_directory))
            console_buyers, warnings = console.normalize_buyers(
                [buyer],
                "中国",
                "电机、减速机",
                enforce_research_copy_rules=True,
            )

        self.assertEqual(cli_buyers[0]["products"], "需核实具体设备")
        self.assertIn("需人工核实具体采购设备", cli_buyers[0]["research_notes"])
        self.assertEqual(console_buyers[0]["products"], "需核实具体设备")
        self.assertTrue(any("示例买家采购品类目前只能确认到大类" in warning for warning in warnings))
