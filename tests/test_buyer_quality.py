import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "ppt-template-batch" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

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

