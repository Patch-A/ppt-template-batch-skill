from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuyerBoardCliSafetyTests(unittest.TestCase):
    def test_help_does_not_make_unsafe_browser_claims(self) -> None:
        scripts = (
            REPO_ROOT / "scripts" / "recover_real_assets.py",
            REPO_ROOT / "scripts" / "run_buyer_board_pipeline.py",
        )
        forbidden = (
            "playwright",
            "most aggressive",
            "real-site recovery",
            "playwright-first",
        )

        for script in scripts:
            with self.subTest(script=script.name):
                result = subprocess.run(
                    [sys.executable, str(script), "--help"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                help_text = result.stdout.lower()
                for phrase in forbidden:
                    self.assertNotIn(phrase, help_text)

    def test_recovery_browser_modes_skip_network_and_record_reason(self) -> None:
        module = load_script_module(
            "recover_real_assets_under_test",
            REPO_ROOT / "scripts" / "recover_real_assets.py",
        )

        for requested_mode in ("auto", "browser"):
            with self.subTest(asset_mode=requested_mode), TemporaryDirectory() as temp_dir:
                workspace = Path(temp_dir)
                (workspace / "buyers.generated.json").write_text(
                    json.dumps([{"name": "Example Buyer", "website": "https://example.com"}]),
                    encoding="utf-8",
                )
                commands: list[list[str]] = []

                def fake_run(command: list[str]) -> None:
                    commands.append(command)
                    output_path = Path(command[command.index("--output") + 1])
                    output_path.write_text(
                        json.dumps([{"name": "Example Buyer", "website": "https://example.com"}]),
                        encoding="utf-8",
                    )
                    report_path = Path(command[command.index("--report-file") + 1])
                    report_path.write_text(json.dumps([{"notes": []}]), encoding="utf-8")

                module.run = fake_run
                original_argv = sys.argv
                sys.argv = [
                    str(REPO_ROOT / "scripts" / "recover_real_assets.py"),
                    "--workspace",
                    str(workspace),
                    "--asset-mode",
                    requested_mode,
                    "--skip-ppt-refresh",
                ]
                try:
                    self.assertEqual(module.main(), 0)
                finally:
                    sys.argv = original_argv

                fetch_command = commands[0]
                self.assertEqual(fetch_command[fetch_command.index("--asset-mode") + 1], "light")
                report = json.loads((workspace / "asset_fetch_report.json").read_text(encoding="utf-8-sig"))
                self.assertIn("browser_skip:network_unsafe", report[0]["notes"])

    def test_pipeline_browser_modes_skip_network_and_record_reason(self) -> None:
        module = load_script_module(
            "run_buyer_board_pipeline_under_test",
            REPO_ROOT / "scripts" / "run_buyer_board_pipeline.py",
        )

        for requested_mode in ("auto", "browser"):
            with self.subTest(asset_mode=requested_mode), TemporaryDirectory() as temp_dir:
                workspace = Path(temp_dir)
                buyers_path = workspace / "buyers.json"
                buyers_path.write_text(
                    json.dumps([{"name": "Example Buyer", "website": "https://example.com"}]),
                    encoding="utf-8",
                )
                commands: list[list[str]] = []

                def fake_run(command: list[str]) -> None:
                    commands.append(command)
                    output_path = Path(command[command.index("--output") + 1])
                    output_path.write_text(
                        json.dumps([{"name": "Example Buyer", "website": "https://example.com"}]),
                        encoding="utf-8",
                    )
                    report_path = Path(command[command.index("--report-file") + 1])
                    report_path.write_text(json.dumps([{"notes": []}]), encoding="utf-8")

                module.run = fake_run
                output_path = module.enrich_buyer_assets(
                    REPO_ROOT / "ppt-template-batch",
                    buyers_path,
                    workspace,
                    False,
                    requested_mode,
                    18000,
                )

                self.assertEqual(output_path, workspace / "buyers.with-assets.json")
                fetch_command = commands[0]
                self.assertEqual(fetch_command[fetch_command.index("--asset-mode") + 1], "light")
                report = json.loads((workspace / "asset_fetch_report.json").read_text(encoding="utf-8-sig"))
                self.assertIn("browser_skip:network_unsafe", report[0]["notes"])


if __name__ == "__main__":
    unittest.main()
