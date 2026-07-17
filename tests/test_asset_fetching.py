import importlib
import json
import sys
import tempfile
import unittest
from base64 import b64encode
from pathlib import Path
from types import SimpleNamespace
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

    def test_validate_asset_url_rejects_private_network_targets(self):
        valid, reason = self.fetch_buyer_assets.validate_asset_url("http://127.0.0.1/logo.png")

        self.assertFalse(valid)
        self.assertIn("private", reason)

    def test_validate_asset_url_rejects_official_redirect_to_different_host(self):
        valid, reason = self.fetch_buyer_assets.validate_asset_url(
            "https://cdn.evil-example.com/logo.png",
            base_host="acme.com",
        )

        self.assertFalse(valid)
        self.assertIn("host", reason)

    def test_read_response_limited_rejects_oversize_without_unbounded_read(self):
        class FakeResponse:
            def __init__(self, chunks):
                self._chunks = list(chunks)
                self.calls = []

            def read(self, size=-1):
                self.calls.append(size)
                if size in (-1, None):
                    raise AssertionError("response.read() must stay bounded")
                return self._chunks.pop(0) if self._chunks else b""

        response = FakeResponse([b"1234", b"56"])

        with self.assertRaisesRegex(ValueError, "response_too_large"):
            self.fetch_buyer_assets.read_response_limited(response, 5)

        self.assertTrue(response.calls)
        self.assertTrue(all(size not in (-1, None) for size in response.calls))

    def test_decode_data_uri_limited_rejects_oversize_payload(self):
        payload = b64encode(b"abcdef").decode("ascii")

        with self.assertRaisesRegex(ValueError, "response_too_large"):
            self.fetch_buyer_assets.decode_data_uri_limited(f"data:image/svg+xml;base64,{payload}", 5)

    def test_logo_rejection_reason_uses_boundary_matching_and_not_page_url(self):
        candidate = self.AssetCandidate(
            src="https://acme.com/assets/acme-logo.svg",
            page="https://acme.com/wholesale-products",
            kind="image",
            alt="Acme logo",
            cls="wholesale-brand",
            origin="official",
        )

        self.assertEqual(self.fetch_buyer_assets.logo_rejection_reason(candidate), "")

    def test_logo_rejection_reason_still_rejects_real_badge_hints(self):
        candidate = self.AssetCandidate(
            src="https://acme.com/assets/certification-badge.svg",
            page="https://acme.com/about",
            kind="image",
            alt="Certification badge",
            cls="trust-badge",
            origin="official",
        )

        self.assertEqual(
            self.fetch_buyer_assets.logo_rejection_reason(candidate),
            "non_brand_badge_or_banner_hint",
        )

    def test_main_skipped_buyers_emit_full_report_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            buyers_path = root / "buyers.json"
            output_path = root / "buyers.with-assets.json"
            assets_dir = root / "assets"
            cache_path = root / "asset-cache.json"
            report_path = root / "asset-report.json"
            buyers_path.write_text(
                json.dumps(
                    [
                        {"name": "Acme", "website": "https://acme.com"},
                        {"name": "Bravo", "website": "https://bravo.com"},
                    ]
                ),
                encoding="utf-8",
            )
            time_values = iter([0.0, 0.0, 0.0, 1.0, 12.0, 12.0])

            with patch.object(
                self.fetch_buyer_assets,
                "process_buyer",
                return_value=(
                    {"name": "Acme", "website": "https://acme.com", "asset_fetch_notes": "ok"},
                    {
                        "name": "Acme",
                        "website": "https://acme.com",
                        "logo_hit": True,
                        "logo_confidence": "high",
                        "logo_source": "official",
                        "logo_url": "https://acme.com/logo.svg",
                        "logo_rejected_candidates": [],
                        "site_hit": True,
                        "site_source": "official",
                        "asset_mode": "light",
                        "asset_logic_version": self.fetch_buyer_assets.ASSET_LOGIC_VERSION,
                        "notes": ["ok"],
                    },
                ),
            ), patch.object(self.fetch_buyer_assets.time, "monotonic", side_effect=lambda: next(time_values, 12.0)), patch.object(
                sys,
                "argv",
                [
                    "fetch_buyer_assets.py",
                    "--buyers",
                    str(buyers_path),
                    "--output",
                    str(output_path),
                    "--assets-dir",
                    str(assets_dir),
                    "--cache-file",
                    str(cache_path),
                    "--report-file",
                    str(report_path),
                    "--max-seconds",
                    "10",
                ],
            ):
                exit_code = self.fetch_buyer_assets.main()

            self.assertEqual(exit_code, 0)
            report_rows = json.loads(report_path.read_text(encoding="utf-8-sig"))
            skipped = report_rows[1]
            self.assertEqual(skipped["name"], "Bravo")
            self.assertEqual(skipped["logo_confidence"], "missing")
            self.assertEqual(skipped["logo_source"], "")
            self.assertEqual(skipped["logo_url"], "")
            self.assertEqual(skipped["logo_rejected_candidates"], [])
            self.assertEqual(skipped["asset_logic_version"], self.fetch_buyer_assets.ASSET_LOGIC_VERSION)
            self.assertEqual(skipped["site_source"], "")
            self.assertEqual(skipped["notes"], ["skipped:asset_fetch_time_budget_exceeded"])
