from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "ppt-template-batch" / "scripts" / "validate_copy_rewrite.py"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_copy_rewrite_under_test", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CopyRewriteSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_allows_bio_only_rewrite_with_frozen_facts(self) -> None:
        before = [
            {
                "name": "示例企业",
                "country": "中国",
                "website": "https://example.com",
                "products": "切菜机、切肉机",
                "bio": "示例企业成立于2012年，主要服务食品加工厂。",
                "evidence": "官网产品页",
            }
        ]
        after = [
            {
                **before[0],
                "bio": "示例企业从2012年开始服务食品加工厂，业务重点很明确。",
            }
        ]

        issues, changed = self.module.compare_payloads(
            before, after, frozenset({"bio"}), 1.5
        )

        self.assertEqual(issues, [])
        self.assertEqual(changed, ["$[0].bio"])

    def test_rejects_product_or_record_order_changes(self) -> None:
        before = [
            {"name": "甲公司", "products": "电机", "bio": "甲公司生产设备。"},
            {"name": "乙公司", "products": "水泵", "bio": "乙公司提供服务。"},
        ]
        after = [before[1], before[0]]

        issues, _ = self.module.compare_payloads(before, after, frozenset({"bio"}), 1.25)

        self.assertTrue(any(item["code"] == "protected_value_changed" for item in issues))

    def test_rejects_changed_numbers_and_removed_identity_anchor(self) -> None:
        before = [{"name": "示例企业", "bio": "示例企业成立于2012年，覆盖3个城市。"}]
        after = [{"name": "示例企业", "bio": "这家公司成立于2018年，覆盖5个城市。"}]

        issues, _ = self.module.compare_payloads(before, after, frozenset({"bio"}), 1.25)
        codes = {item["code"] for item in issues}

        self.assertIn("fact_tokens_changed", codes)
        self.assertIn("identity_anchor_removed", codes)

    def test_rejects_duplicate_or_removed_fact_tokens(self) -> None:
        before = [{"name": "示例企业", "bio": "示例企业在2020年服务3家工厂，2020年完成扩建。"}]
        after = [{"name": "示例企业", "bio": "示例企业在2020年服务3家工厂并完成扩建。"}]

        issues, _ = self.module.compare_payloads(before, after, frozenset({"bio"}), 1.25)

        self.assertTrue(any(item["code"] == "fact_tokens_changed" for item in issues))

    def test_rejects_internal_process_terms_in_customer_copy(self) -> None:
        before = [{"name": "示例企业", "bio": "示例企业提供工业服务。"}]
        after = [{"name": "示例企业", "bio": "示例企业已进入accepted候选池。"}]

        issues, _ = self.module.compare_payloads(before, after, frozenset({"bio"}), 2.0)

        self.assertTrue(any(item["code"] == "forbidden_customer_term" for item in issues))

    def test_generic_profile_allows_identity_wording_to_change(self) -> None:
        before = [{"name": "示例产品", "summary": "示例产品整理了2026年3项公开数据。"}]
        after = [{"name": "示例产品", "summary": "这份材料整理了2026年3项公开数据。"}]

        issues, changed = self.module.compare_payloads(
            before, after, frozenset({"summary"}), 1.5, profile="generic"
        )

        self.assertEqual(issues, [])
        self.assertEqual(changed, ["$[0].summary"])

    def test_buyer_profile_keeps_identity_and_process_word_checks(self) -> None:
        before = [{"name": "示例企业", "bio": "示例企业提供工业服务。"}]
        after = [{"name": "示例企业", "bio": "这家公司已进入accepted候选池。"}]

        issues, _ = self.module.compare_payloads(
            before, after, frozenset({"bio"}), 2.0, profile="buyer"
        )
        codes = {item["code"] for item in issues}

        self.assertIn("identity_anchor_removed", codes)
        self.assertIn("forbidden_customer_term", codes)


if __name__ == "__main__":
    unittest.main()
