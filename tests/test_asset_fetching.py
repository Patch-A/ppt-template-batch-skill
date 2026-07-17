import importlib
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "ppt-template-batch" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

class AssetFetchingRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fetch_buyer_assets = importlib.import_module("fetch_buyer_assets")
        cls.AssetCandidate = cls.fetch_buyer_assets.AssetCandidate

    def test_official_acme_rgb_logo_candidate_is_not_rejected(self):
        candidate = self.AssetCandidate(
            src="https://acme.com/assets/acme-logo-rgb.svg",
            page="https://acme.com/wholesale-products",
            kind="image",
            alt="Acme logo",
            cls="brand-mark",
            origin="official",
        )

        ranked = self.fetch_buyer_assets.rank_logo_candidates([candidate], "Acme", "acme.com")

        self.assertIn(candidate, ranked)

    def test_logo_only_cache_entry_retries_missing_site_asset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logo_path = root / "acme-logo.png"
            logo_path.write_bytes(b"logo")
            cache = {
                "https://acme.com": {
                    "asset_logic_version": self.fetch_buyer_assets.ASSET_LOGIC_VERSION,
                    "logo_path": str(logo_path),
                    "site_image_path": "",
                }
            }
            calls = []
            site_path = root / "assets" / "acme-site.jpg"
            visual = self.AssetCandidate(
                src="https://acme.com/assets/conveyor-line.jpg",
                page="https://acme.com/wholesale-products",
                kind="image",
                origin="official",
            )

            def discover(*args, **kwargs):
                calls.append((args, kwargs))
                return "https://acme.com", [], [visual], ["site:recovered"]

            def download(candidate, output_path, kind):
                self.assertEqual(kind, "site")
                site_path.parent.mkdir(parents=True, exist_ok=True)
                site_path.write_bytes(b"recovered site")
                return site_path, {"bytes": site_path.stat().st_size}

            with patch.object(self.fetch_buyer_assets, "discover_assets_for_domain", side_effect=discover), patch.object(
                self.fetch_buyer_assets, "download_asset", side_effect=download
            ), patch.object(
                self.fetch_buyer_assets,
                "prepare_site_image",
                return_value=SimpleNamespace(output_path=site_path, mode="test", retention=1.0, upscale=False),
            ):
                buyer, report = self.fetch_buyer_assets.process_buyer(
                    {"name": "Acme", "website": "https://acme.com"},
                    root / "assets",
                    cache,
                    enable_ai_visual_fallback=False,
                    asset_mode="light",
                    browser_timeout_ms=1000,
                )

            self.assertEqual(len(calls), 1)
            self.assertEqual(buyer["site_image_path"], str(site_path))
            self.assertEqual(cache["https://acme.com"]["site_image_path"], str(site_path))
            self.assertTrue(report["site_hit"])
            self.assertEqual(report["site_source"], "official")
            self.assertTrue(site_path.is_file())
