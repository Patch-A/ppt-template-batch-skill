import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "ppt-template-batch" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import fetch_buyer_assets
from fetch_buyer_assets import AssetCandidate, process_buyer, rank_logo_candidates


class AssetFetchingRegressionTests(unittest.TestCase):
    def test_official_acme_rgb_logo_candidate_is_not_rejected(self):
        candidate = AssetCandidate(
            src="https://acme.com/assets/acme-logo-rgb.svg",
            page="https://acme.com/wholesale-products",
            kind="image",
            alt="Acme logo",
            cls="brand-mark",
            origin="official",
        )

        ranked = rank_logo_candidates([candidate], "Acme", "acme.com")

        self.assertIn(candidate, ranked)

    def test_logo_only_cache_entry_retries_missing_site_asset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logo_path = root / "acme-logo.png"
            logo_path.write_bytes(b"logo")
            cache = {
                "https://acme.com": {
                    "asset_logic_version": fetch_buyer_assets.ASSET_LOGIC_VERSION,
                    "logo_path": str(logo_path),
                    "site_image_path": "",
                }
            }
            calls = []

            def discover(*args, **kwargs):
                calls.append((args, kwargs))
                return "https://acme.com", [], [], ["site:missing"]

            with patch.object(fetch_buyer_assets, "discover_assets_for_domain", side_effect=discover):
                process_buyer(
                    {"name": "Acme", "website": "https://acme.com"},
                    root / "assets",
                    cache,
                    enable_ai_visual_fallback=False,
                    asset_mode="light",
                    browser_timeout_ms=1000,
                )

            self.assertEqual(len(calls), 1)

