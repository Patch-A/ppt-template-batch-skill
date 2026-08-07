from __future__ import annotations

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "ppt-template-batch" / "scripts" / "fetch_record_assets.py"


def load_module():
    spec = importlib.util.spec_from_file_location("fetch_record_assets_under_test", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GenericAssetFetchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_unpack_and_repack_preserve_generic_root_fields(self) -> None:
        payload = {"globals": {"title": "目录"}, "records": [{"title": "A"}]}

        records, shape = self.module.unpack_records(payload)
        result = self.module.repack_records(payload, [{"title": "B"}], shape)

        self.assertEqual(records, [{"title": "A"}])
        self.assertEqual(result["globals"], payload["globals"])
        self.assertEqual(result["records"], [{"title": "B"}])

    def test_custom_fields_are_mapped_to_shared_asset_engine(self) -> None:
        processed = {
            "name": "Acme",
            "website": "https://acme.example",
            "logo_path": "assets/acme.svg",
            "site_image_path": "assets/acme.jpg",
            "asset_fetch_notes": "light:complete",
        }
        report = {"logo_hit": True, "site_hit": True}
        with TemporaryDirectory() as temp_dir, patch.object(
            self.module.asset_fetcher, "process_buyer", return_value=(processed, report)
        ) as process:
            record, result = self.module.process_record(
                {"brand": "Acme", "official_url": "https://acme.example"},
                "official_url",
                "brand",
                "brand_mark",
                "hero_path",
                Path(temp_dir),
                {},
                "crawl4ai",
                8000,
                35,
            )

        canonical = process.call_args.args[0]
        self.assertEqual(canonical["name"], "Acme")
        self.assertEqual(canonical["website"], "https://acme.example")
        self.assertEqual(record["brand_mark"], "assets/acme.svg")
        self.assertEqual(record["hero_path"], "assets/acme.jpg")
        self.assertEqual(result["url_field"], "official_url")

    def test_missing_url_is_reported_without_network_work(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.object(
            self.module.asset_fetcher, "process_buyer"
        ) as process:
            record, report = self.module.process_record(
                {"title": "No site"},
                "official_url",
                "title",
                "logo_path",
                "hero_path",
                Path(temp_dir),
                {},
                "light",
                8000,
                35,
            )

        process.assert_not_called()
        self.assertEqual(record["asset_fetch_notes"], "missing_url_field:official_url")
        self.assertEqual(report["notes"], ["missing_url_field:official_url"])


if __name__ == "__main__":
    unittest.main()
