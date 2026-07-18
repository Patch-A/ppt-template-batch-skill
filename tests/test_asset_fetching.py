import importlib
from io import StringIO
import json
import queue
import socket
import sys
import tempfile
import threading
import time
import unittest
from base64 import b64encode
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse


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

    def test_download_asset_preserves_stable_fetch_rejection_reasons(self):
        candidate = self.AssetCandidate(
            src="https://acme.com/assets/acme-logo.svg",
            page="https://acme.com",
            kind="image",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            for reason in (
                "invalid_scheme",
                "invalid_host",
                "local_host",
                "invalid_ip_literal",
                "non_public_ip",
                "different_host",
                "host_resolution_failed",
                "response_too_large",
                "too_many_redirects",
            ):
                with self.subTest(reason=reason), patch.object(
                    self.fetch_buyer_assets,
                    "fetch_url",
                    side_effect=ValueError(reason),
                ):
                    downloaded, meta = self.fetch_buyer_assets.download_asset(
                        candidate,
                        Path(temp_dir) / "acme-logo",
                        "logo",
                    )

                self.assertIsNone(downloaded)
                self.assertEqual(meta, {"reason": reason})

    def test_download_asset_keeps_type_only_for_unclassified_fetch_errors(self):
        candidate = self.AssetCandidate(
            src="https://acme.com/assets/acme-logo.svg",
            page="https://acme.com",
            kind="image",
        )

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            self.fetch_buyer_assets,
            "fetch_url",
            side_effect=RuntimeError("connection failed"),
        ):
            downloaded, meta = self.fetch_buyer_assets.download_asset(
                candidate,
                Path(temp_dir) / "acme-logo",
                "logo",
            )

        self.assertIsNone(downloaded)
        self.assertEqual(meta, {"reason": "download_failed:RuntimeError"})

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

    def test_site_cache_entry_survives_stale_logo_and_retries_only_logo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            stale_logo_path = root / "missing-logo.png"
            site_path = root / "assets" / "acme-site.jpg"
            site_path.parent.mkdir(parents=True, exist_ok=True)
            site_path.write_bytes(b"cached site")
            cache = {
                "https://acme.com": {
                    "asset_logic_version": self.fetch_buyer_assets.ASSET_LOGIC_VERSION,
                    "logo_path": str(stale_logo_path),
                    "site_image_path": str(site_path),
                    "site_source": "official",
                }
            }
            logo_path = root / "assets" / "acme-logo.svg"
            logo = self.AssetCandidate(
                src="https://acme.com/assets/acme-logo.svg",
                page="https://acme.com",
                kind="image",
                origin="official",
                score=40,
            )

            def download(candidate, output_path, kind):
                self.assertEqual(kind, "logo")
                logo_path.write_bytes(b"<svg></svg>")
                return logo_path, {"bytes": logo_path.stat().st_size}

            with patch.object(
                self.fetch_buyer_assets,
                "discover_assets_for_domain",
                return_value=("https://acme.com", [logo], [], ["logo:recovered"]),
            ), patch.object(self.fetch_buyer_assets, "download_asset", side_effect=download), patch.object(
                self.fetch_buyer_assets, "prepare_site_image"
            ) as prepare:
                buyer, report = self.fetch_buyer_assets.process_buyer(
                    {"name": "Acme", "website": "https://acme.com"},
                    root / "assets",
                    cache,
                    enable_ai_visual_fallback=False,
                    asset_mode="light",
                    browser_timeout_ms=1000,
                )

            prepare.assert_not_called()
            self.assertEqual(buyer["site_image_path"], str(site_path))
            self.assertEqual(cache["https://acme.com"]["site_image_path"], str(site_path))
            self.assertEqual(cache["https://acme.com"]["logo_path"], str(logo_path))
            self.assertTrue(report["logo_hit"])
            self.assertTrue(report["site_hit"])

    def test_logo_cache_entry_survives_stale_site_and_retries_only_site(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logo_path = root / "assets" / "acme-logo.svg"
            logo_path.parent.mkdir(parents=True, exist_ok=True)
            logo_path.write_bytes(b"<svg></svg>")
            stale_site_path = root / "missing-site.jpg"
            cache = {
                "https://acme.com": {
                    "asset_logic_version": self.fetch_buyer_assets.ASSET_LOGIC_VERSION,
                    "logo_path": str(logo_path),
                    "site_image_path": str(stale_site_path),
                    "logo_confidence": "high",
                    "logo_source": "official",
                    "logo_url": "https://acme.com/assets/acme-logo.svg",
                }
            }
            site_path = root / "assets" / "acme-site.jpg"
            visual = self.AssetCandidate(
                src="https://acme.com/assets/conveyor-line.jpg",
                page="https://acme.com",
                kind="image",
                origin="official",
                score=30,
            )

            def download(candidate, output_path, kind):
                self.assertEqual(kind, "site")
                site_path.write_bytes(b"recovered site")
                return site_path, {"bytes": site_path.stat().st_size}

            with patch.object(
                self.fetch_buyer_assets,
                "discover_assets_for_domain",
                return_value=("https://acme.com", [], [visual], ["site:recovered"]),
            ), patch.object(self.fetch_buyer_assets, "download_asset", side_effect=download), patch.object(
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

            self.assertEqual(buyer["logo_path"], str(logo_path))
            self.assertEqual(cache["https://acme.com"]["logo_path"], str(logo_path))
            self.assertEqual(cache["https://acme.com"]["site_image_path"], str(site_path))
            self.assertTrue(report["logo_hit"])
            self.assertTrue(report["site_hit"])

    def test_validate_asset_url_rejects_invalid_ip_literals(self):
        valid, reason = self.fetch_buyer_assets.validate_asset_url("http://999.999.999.999/logo.png")

        self.assertFalse(valid)
        self.assertEqual(reason, "invalid_ip_literal")

    def test_validate_asset_url_rejects_private_network_targets(self):
        valid, reason = self.fetch_buyer_assets.validate_asset_url("http://127.0.0.1/logo.png")

        self.assertFalse(valid)
        self.assertEqual(reason, "non_public_ip")

    def test_validate_asset_url_rejects_localhost_names(self):
        for host in ["localhost", "localhost.", "assets.localhost", "ASSETS.LOCALHOST."]:
            with self.subTest(host=host):
                valid, reason = self.fetch_buyer_assets.validate_asset_url(f"https://{host}/logo.png")

                self.assertFalse(valid)
                self.assertEqual(reason, "local_host")

    def test_validate_asset_url_rejects_loopback_literal_bypasses(self):
        for host in ["127.1", "2130706433", "0x7f000001"]:
            with self.subTest(host=host):
                valid, reason = self.fetch_buyer_assets.validate_asset_url(f"https://{host}/logo.png")

                self.assertFalse(valid)
                self.assertEqual(reason, "non_public_ip")

    def test_validate_asset_url_rejects_non_public_ip_literals(self):
        for host in [
            "127.0.0.1",
            "10.0.0.1",
            "169.254.1.1",
            "192.0.2.1",
            "224.0.0.1",
            "0.0.0.0",
            "[::1]",
            "[fc00::1]",
            "[fe80::1]",
            "[2001:db8::1]",
            "[ff02::1]",
            "[::]",
        ]:
            with self.subTest(host=host):
                valid, reason = self.fetch_buyer_assets.validate_asset_url(f"https://{host}/logo.png")

                self.assertFalse(valid)
                self.assertEqual(reason, "non_public_ip")

    def test_validate_asset_url_resolves_hostnames_and_rejects_non_public_answers(self):
        dns_answers = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443)),
        ]

        with patch("socket.getaddrinfo", return_value=dns_answers) as getaddrinfo:
            valid, reason = self.fetch_buyer_assets.validate_asset_url("https://cdn.acme.com/logo.png")

        self.assertFalse(valid)
        self.assertEqual(reason, "non_public_ip")
        getaddrinfo.assert_called_once()

    def test_validate_asset_url_fails_closed_when_hostname_resolution_fails(self):
        with patch("socket.getaddrinfo", side_effect=socket.gaierror):
            valid, reason = self.fetch_buyer_assets.validate_asset_url("https://cdn.acme.com/logo.png")

        self.assertFalse(valid)
        self.assertEqual(reason, "host_resolution_failed")

    def test_validate_asset_url_allows_same_site_cdn_subdomain_after_www_normalization(self):
        dns_answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

        with patch("socket.getaddrinfo", return_value=dns_answers):
            valid, reason = self.fetch_buyer_assets.validate_asset_url(
                "https://CDN.Acme.com/logo.png",
                base_host="www.acme.com",
            )

        self.assertTrue(valid)
        self.assertEqual(reason, "")

    def test_validate_asset_url_rejects_different_site_after_www_normalization(self):
        dns_answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

        with patch("socket.getaddrinfo", return_value=dns_answers):
            valid, reason = self.fetch_buyer_assets.validate_asset_url(
                "https://cdn.evil-example.com/logo.png",
                base_host="https://www.acme.com",
            )

        self.assertFalse(valid)
        self.assertEqual(reason, "different_host")

    def test_validate_asset_url_rejects_official_redirect_to_different_host(self):
        valid, reason = self.fetch_buyer_assets.validate_asset_url(
            "https://cdn.evil-example.com/logo.png",
            base_host="acme.com",
        )

        self.assertFalse(valid)
        self.assertIn("host", reason)

    def test_decode_data_uri_limited_rejects_oversize_payload(self):
        payload = b64encode(b"abcdef").decode("ascii")

        with self.assertRaisesRegex(ValueError, "response_too_large"):
            self.fetch_buyer_assets.decode_data_uri_limited(f"data:image/svg+xml;base64,{payload}", 5)

    def test_decode_percent_data_uri_limited_rejects_incrementally(self):
        def fail_full_decode(payload):
            if payload == "abcdef":
                raise AssertionError("must not decode full oversized data URI payload")
            return payload.encode("ascii")

        with patch.object(self.fetch_buyer_assets, "unquote_to_bytes", side_effect=fail_full_decode):
            with self.assertRaisesRegex(ValueError, "response_too_large"):
                self.fetch_buyer_assets.decode_data_uri_limited("data:text/plain,abcdef", 5)

    def test_curl_max_filesize_exit_raises_response_too_large(self):
        with patch("socket.getaddrinfo", return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ]), patch(
            "subprocess.run",
            return_value=SimpleNamespace(returncode=63, stderr=b"Maximum file size exceeded", stdout=b""),
        ):
            with self.assertRaisesRegex(ValueError, "response_too_large"):
                self.fetch_buyer_assets.fetch_url_with_curl("https://acme.com/logo.png", max_bytes=5)

    def test_browser_mode_skips_network_with_public_api(self):
        final_url, logos, visuals, notes = self.fetch_buyer_assets.discover_assets_for_domain_browser(
            "acme.com",
            "Acme",
            1000,
        )

        self.assertIsNone(final_url)
        self.assertEqual(logos, [])
        self.assertEqual(visuals, [])
        self.assertIn("browser_skip:network_unsafe", notes)

    def test_browser_modes_have_no_playwright_runtime_dependency(self):
        self.assertFalse(hasattr(self.fetch_buyer_assets, "import_playwright"))

    def test_auto_mode_skips_network_with_public_api(self):
        with patch.object(
            self.fetch_buyer_assets,
            "discover_assets_for_domain_light",
            return_value=("https://acme.com", [], [], ["light:empty"]),
        ), patch.object(
            self.fetch_buyer_assets,
            "get_env_var",
            return_value="1",
        ):
            final_url, logos, visuals, notes = self.fetch_buyer_assets.discover_assets_for_domain(
                "acme.com",
                "Acme",
                "auto",
                1000,
            )

        self.assertEqual(final_url, "https://acme.com")
        self.assertEqual(logos, [])
        self.assertEqual(visuals, [])
        self.assertIn("browser_skip:network_unsafe", notes)

    def test_asset_mode_help_describes_browser_network_safety_skip(self):
        stdout = StringIO()
        with patch.object(sys, "argv", ["fetch_buyer_assets.py", "--help"]), patch.object(sys, "stdout", stdout):
            with self.assertRaises(SystemExit) as exit_info:
                self.fetch_buyer_assets.main()

        self.assertEqual(exit_info.exception.code, 0)
        help_output = " ".join(stdout.getvalue().split())
        self.assertIn("browser and auto browser fallback are skipped for network safety", help_output)
        self.assertIn("retained for CLI compatibility", help_output)

    def test_curl_disables_curlrc_and_proxies_before_connecting(self):
        commands = []

        def run_curl(command, **_kwargs):
            commands.append(command)
            Path(command[command.index("-o") + 1]).write_bytes(b"logo")
            return SimpleNamespace(
                returncode=0,
                stderr=b"",
                stdout=b"https://acme.com/logo.png\n200\nimage/png\n",
            )

        dns_answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with patch("socket.getaddrinfo", return_value=dns_answers), patch("subprocess.run", side_effect=run_curl):
            self.fetch_buyer_assets.fetch_url_with_curl("https://acme.com/logo.png")

        self.assertEqual(commands[0][:2], ["curl", "-q"])
        self.assertEqual(commands[0][2:4], ["--noproxy", "*"])
        self.assertNotIn("-L", commands[0])

    def test_curl_normalizes_tail_dot_hostname_before_pinning(self):
        commands = []
        normalized_url = "https://user:pass@acme.com:8443/logo.png?size=1#fragment"

        def run_curl(command, **_kwargs):
            commands.append(command)
            Path(command[command.index("-o") + 1]).write_bytes(b"logo")
            return SimpleNamespace(
                returncode=0,
                stderr=b"",
                stdout=f"{normalized_url}\n200\nimage/png\n".encode("utf-8"),
            )

        dns_answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with patch("socket.getaddrinfo", return_value=dns_answers), patch("subprocess.run", side_effect=run_curl):
            self.fetch_buyer_assets.fetch_url_with_curl(
                "https://user:pass@AcMe.Com.:8443/logo.png?size=1#fragment"
            )

        resolve_entry = commands[0][commands[0].index("--resolve") + 1]
        self.assertEqual(commands[0][-1], normalized_url)
        self.assertEqual(urlparse(commands[0][-1]).hostname, resolve_entry.split(":", 1)[0])
        self.assertEqual(resolve_entry, "acme.com:8443:93.184.216.34")

    def test_curl_normalizes_idn_hostname_for_same_site_pinning(self):
        commands = []
        normalized_url = "https://cdn.xn--bcher-kva.example/logo.png"

        def run_curl(command, **_kwargs):
            commands.append(command)
            Path(command[command.index("-o") + 1]).write_bytes(b"logo")
            return SimpleNamespace(
                returncode=0,
                stderr=b"",
                stdout=f"{normalized_url}\n200\nimage/png\n".encode("utf-8"),
            )

        dns_answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with patch("socket.getaddrinfo", return_value=dns_answers) as getaddrinfo, patch(
            "subprocess.run",
            side_effect=run_curl,
        ):
            self.fetch_buyer_assets.fetch_url_with_curl(
                "https://cdn.BÜCHER.example./logo.png",
                base_host="www.BÜCHER.example.",
            )

        resolve_entry = commands[0][commands[0].index("--resolve") + 1]
        self.assertEqual(commands[0][-1], normalized_url)
        self.assertEqual(urlparse(commands[0][-1]).hostname, resolve_entry.split(":", 1)[0])
        self.assertEqual(resolve_entry, "cdn.xn--bcher-kva.example:443:93.184.216.34")
        getaddrinfo.assert_called_once_with("cdn.xn--bcher-kva.example", None)

    def test_curl_removes_idna_normalized_ideographic_full_stop_before_pinning(self):
        commands = []
        normalized_url = "https://example.com/logo.png"

        def run_curl(command, **_kwargs):
            commands.append(command)
            Path(command[command.index("-o") + 1]).write_bytes(b"logo")
            return SimpleNamespace(
                returncode=0,
                stderr=b"",
                stdout=f"{normalized_url}\n200\nimage/png\n".encode("utf-8"),
            )

        dns_answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with patch("socket.getaddrinfo", return_value=dns_answers) as getaddrinfo, patch(
            "subprocess.run",
            side_effect=run_curl,
        ):
            self.fetch_buyer_assets.fetch_url_with_curl("https://example.com\u3002/logo.png")

        resolve_entry = commands[0][commands[0].index("--resolve") + 1]
        self.assertEqual(commands[0][-1], normalized_url)
        self.assertEqual(resolve_entry, "example.com:443:93.184.216.34")
        getaddrinfo.assert_called_once_with("example.com", None)

    def test_blocked_dns_respects_deadline_before_starting_curl(self):
        commands = []
        entered_dns = threading.Event()
        release_dns = threading.Event()
        result_queue = queue.Queue(maxsize=1)

        def blocked_getaddrinfo(*_args):
            entered_dns.set()
            release_dns.wait()
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

        def run_curl(command, **_kwargs):
            commands.append(command)
            raise AssertionError("curl must not start after DNS deadline expiry")

        previous_deadline = self.fetch_buyer_assets.FETCH_DEADLINE
        self.fetch_buyer_assets.FETCH_DEADLINE = time.monotonic() + 10

        def fetch_in_thread():
            try:
                self.fetch_buyer_assets.fetch_url_with_curl("https://acme.com/logo.png")
            except BaseException as exc:
                result_queue.put(exc)

        try:
            with patch("socket.getaddrinfo", side_effect=blocked_getaddrinfo), patch(
                "subprocess.run",
                side_effect=run_curl,
            ):
                fetch_thread = threading.Thread(target=fetch_in_thread)
                fetch_thread.start()
                self.assertTrue(entered_dns.wait(timeout=1))
                self.fetch_buyer_assets.FETCH_DEADLINE = time.monotonic() - 1
                release_dns.set()
                error = result_queue.get(timeout=1)
                fetch_thread.join(timeout=1)
        finally:
            release_dns.set()
            self.fetch_buyer_assets.FETCH_DEADLINE = previous_deadline

        self.assertIsInstance(error, TimeoutError)
        self.assertEqual(str(error), "asset_fetch_per_buyer_timeout")
        self.assertEqual(commands, [])

    def test_redirect_chain_stops_before_second_connection_when_deadline_expires(self):
        commands = []

        def run_curl(command, **_kwargs):
            commands.append(command)
            if len(commands) > 1:
                Path(command[command.index("-o") + 1]).write_bytes(b"logo")
                stdout = b"https://cdn.acme.com/logo.png\n200\nimage/png\n"
            else:
                stdout = b"https://acme.com/logo.png\n302\ntext/html\nhttps://cdn.acme.com/logo.png"
            return SimpleNamespace(
                returncode=0,
                stderr=b"",
                stdout=stdout,
            )

        dns_answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        previous_deadline = self.fetch_buyer_assets.FETCH_DEADLINE
        self.fetch_buyer_assets.FETCH_DEADLINE = 1.0
        try:
            with patch.object(self.fetch_buyer_assets.time, "monotonic", side_effect=[0.0, 0.0, 0.0, 0.0, 1.0]), patch(
                "socket.getaddrinfo",
                return_value=dns_answers,
            ), patch("subprocess.run", side_effect=run_curl):
                with self.assertRaisesRegex(TimeoutError, "asset_fetch_per_buyer_timeout"):
                    self.fetch_buyer_assets.fetch_url_with_curl("https://acme.com/logo.png")
        finally:
            self.fetch_buyer_assets.FETCH_DEADLINE = previous_deadline

        self.assertEqual(len(commands), 1)

    def test_curl_pins_hostname_to_validated_public_ip(self):
        commands = []

        def run_curl(command, **kwargs):
            commands.append(command)
            Path(command[command.index("-o") + 1]).write_bytes(b"logo")
            return SimpleNamespace(
                returncode=0,
                stderr=b"",
                stdout=b"https://acme.com/logo.png\n200\nimage/png\n",
            )

        dns_answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with patch("socket.getaddrinfo", return_value=dns_answers), patch("subprocess.run", side_effect=run_curl):
            final_url, body, content_type = self.fetch_buyer_assets.fetch_url_with_curl(
                "https://acme.com/logo.png"
            )

        self.assertEqual(final_url, "https://acme.com/logo.png")
        self.assertEqual(body, b"logo")
        self.assertEqual(content_type, "image/png")
        self.assertIn("--resolve", commands[0])
        self.assertEqual(commands[0][commands[0].index("--resolve") + 1], "acme.com:443:93.184.216.34")

    def test_curl_pins_ipv6_hostname_with_bracketed_resolve_address(self):
        commands = []

        def run_curl(command, **kwargs):
            commands.append(command)
            Path(command[command.index("-o") + 1]).write_bytes(b"logo")
            return SimpleNamespace(
                returncode=0,
                stderr=b"",
                stdout=b"https://acme.com/logo.png\n200\nimage/png\n",
            )

        dns_answers = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700:4700::1111", 443, 0, 0))
        ]
        with patch("socket.getaddrinfo", return_value=dns_answers), patch("subprocess.run", side_effect=run_curl):
            self.fetch_buyer_assets.fetch_url_with_curl("https://acme.com/logo.png")

        self.assertEqual(
            commands[0][commands[0].index("--resolve") + 1],
            "acme.com:443:[2606:4700:4700::1111]",
        )

    def test_curl_rejects_localhost_redirect_before_second_connection(self):
        commands = []

        def run_curl(command, **kwargs):
            commands.append(command)
            return SimpleNamespace(
                returncode=0,
                stderr=b"",
                stdout=(
                    b"https://acme.com/logo.png\n302\ntext/html\n"
                    b"http://localhost/internal-logo.png"
                ),
            )

        dns_answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with patch("socket.getaddrinfo", return_value=dns_answers), patch("subprocess.run", side_effect=run_curl):
            with self.assertRaisesRegex(ValueError, "local_host"):
                self.fetch_buyer_assets.fetch_url_with_curl("https://acme.com/logo.png")

        self.assertEqual(len(commands), 1)
        self.assertNotIn("-L", commands[0])

    def test_curl_allows_public_same_site_cdn_redirect_with_pinned_connections(self):
        commands = []

        def resolve(host, *_args):
            answers = {
                "acme.com": "93.184.216.34",
                "cdn.acme.com": "1.1.1.1",
            }
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (answers[host], 443))]

        def run_curl(command, **kwargs):
            commands.append(command)
            Path(command[command.index("-o") + 1]).write_bytes(b"cdn-logo")
            if len(commands) == 1:
                stdout = b"https://acme.com/logo.png\n302\ntext/html\nhttps://cdn.acme.com/logo.png"
            else:
                stdout = b"https://cdn.acme.com/logo.png\n200\nimage/png\n"
            return SimpleNamespace(returncode=0, stderr=b"", stdout=stdout)

        with patch("socket.getaddrinfo", side_effect=resolve), patch("subprocess.run", side_effect=run_curl):
            final_url, body, content_type = self.fetch_buyer_assets.fetch_url_with_curl(
                "https://acme.com/logo.png",
                base_host="www.acme.com",
            )

        self.assertEqual(final_url, "https://cdn.acme.com/logo.png")
        self.assertEqual(body, b"cdn-logo")
        self.assertEqual(content_type, "image/png")
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[0][commands[0].index("--resolve") + 1], "acme.com:443:93.184.216.34")
        self.assertEqual(commands[1][commands[1].index("--resolve") + 1], "cdn.acme.com:443:1.1.1.1")

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

    def test_logo_ranking_uses_only_basename_alt_and_class_evidence(self):
        directory_only = self.AssetCandidate(
            src="https://acme.com/brand/logo/assets/image.svg?logo=1",
            page="https://acme.com/logo",
            kind="logo",
            alt="",
            cls="",
            origin="official",
        )
        real_evidence = self.AssetCandidate(
            src="https://acme.com/assets/image.svg",
            page="https://acme.com",
            kind="image",
            alt="Acme logo",
            cls="brand-mark",
            origin="official",
        )

        ranked = self.fetch_buyer_assets.rank_logo_candidates(
            [directory_only, real_evidence],
            "Acme",
            "acme.com",
        )

        self.assertNotIn(directory_only, ranked)
        self.assertIn(real_evidence, ranked)

    def test_parse_page_classifies_logo_images_from_basename_alt_and_class_only(self):
        logos, visuals, _ = self.fetch_buyer_assets.parse_page(
            "https://acme.com",
            (
                '<img src="/brand/logo/assets/image.svg?logo=1" alt="" class="">'
                '<img src="/assets/image.svg" alt="Acme logo" class="brand-mark">'
            ),
        )

        self.assertNotIn(
            "https://acme.com/brand/logo/assets/image.svg?logo=1",
            [candidate.src for candidate in logos],
        )
        self.assertIn(
            "https://acme.com/assets/image.svg",
            [candidate.src for candidate in logos],
        )
        self.assertIn(
            "https://acme.com/brand/logo/assets/image.svg?logo=1",
            [candidate.src for candidate in visuals],
        )

    def test_parse_page_keeps_link_icon_as_logo_candidate(self):
        logos, visuals, _ = self.fetch_buyer_assets.parse_page(
            "https://acme.com",
            '<link rel="icon" href="/assets/site-mark.svg">',
        )

        self.assertIn(
            "https://acme.com/assets/site-mark.svg",
            [candidate.src for candidate in logos],
        )
        self.assertEqual(visuals, [])

    def test_logo_rejection_ignores_url_directories_page_and_kind(self):
        candidate = self.AssetCandidate(
            src="https://acme.com/certification/assets/acme-logo.svg",
            page="https://acme.com/certificate",
            kind="certificate",
            alt="Acme logo",
            cls="brand-mark",
            origin="official",
        )

        self.assertEqual(
            self.fetch_buyer_assets.logo_candidate_rejection_reason(candidate, "Acme", "acme.com"),
            "",
        )

    def test_logo_rejection_ignores_url_query(self):
        candidate = self.AssetCandidate(
            src="https://acme.com/assets/acme-logo.svg?certificate=badge",
            page="https://acme.com",
            kind="image",
            alt="Acme logo",
            cls="brand-mark",
            origin="official",
        )

        self.assertEqual(self.fetch_buyer_assets.logo_rejection_reason(candidate), "")

    def test_candidate_brand_tokens_include_class(self):
        candidate = self.AssetCandidate(
            src="https://acme.com/assets/logo.svg",
            page="https://acme.com",
            kind="image",
            alt="Corporate identity",
            cls="acme-brand",
            origin="official",
        )

        self.assertIn("acme", self.fetch_buyer_assets.candidate_brand_tokens(candidate))

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
            normal = report_rows[0]
            self.assertEqual(skipped["name"], "Bravo")
            self.assertEqual(skipped["logo_confidence"], "missing")
            self.assertEqual(skipped["logo_source"], "")
            self.assertEqual(skipped["logo_url"], "")
            self.assertEqual(skipped["logo_rejected_candidates"], [])
            self.assertEqual(skipped["asset_logic_version"], self.fetch_buyer_assets.ASSET_LOGIC_VERSION)
            self.assertEqual(skipped["site_source"], "")
            self.assertEqual(skipped["notes"], ["skipped:asset_fetch_time_budget_exceeded"])
            self.assertEqual(set(skipped), set(normal))
            self.assertEqual(normal["elapsed_seconds"], 1.0)
            self.assertEqual(skipped["elapsed_seconds"], 12.0)
