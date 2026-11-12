import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from cognisight.recognition.cli import main


class CliTests(unittest.TestCase):
    def test_help_and_hardware_probe_do_not_import_hardware(self):
        with redirect_stdout(io.StringIO()) as out:
            result = main(["doctor"])
        report = json.loads(out.getvalue())
        self.assertIn("architecture", report)
        self.assertIn("unverified", report["qualification"])
        self.assertEqual(result, 0)

    def test_run_rejects_missing_assets_without_creating_patient_state(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / "missing.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "run",
                            "--config",
                            str(config),
                            "--state-dir",
                            str(Path(root) / "private"),
                        ]
                    ),
                    2,
                )
            self.assertFalse((Path(root) / "private").exists())

    def test_password_longer_than_login_limit_is_rejected_before_state_write(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "private"
            secret = "x" * 257
            with patch("cognisight.recognition.cli.getpass.getpass", side_effect=[secret, secret]), \
                    redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["password", "--state-dir", str(state)]), 2)
            self.assertFalse(state.exists())
            self.assertNotIn(secret, output.getvalue())

    def test_password_rejects_repo_state_before_prompt_or_write(self):
        from unittest.mock import patch
        from cognisight.recognition.cli import validate_state_dir

        with self.assertRaises(ValueError):
            validate_state_dir(Path(__file__).resolve().parents[1] / "private-data")


class OptionalCliTests(unittest.TestCase):
    def test_run_help_explains_optional_monitoring_without_hardware_imports(self):
        with redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(SystemExit) as result:
                main(["run", "--help"])
        self.assertEqual(result.exception.code, 0)
        self.assertIn("GPSD", out.getvalue())
        self.assertIn("caregiver", out.getvalue())

    def test_port_collision_is_rejected_before_private_state_creation(self):
        config = {"caregiver": {"enabled": True, "backend_port": 8765}}
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "private"
            with (
                patch("cognisight.recognition.config.load_config", return_value=config),
                patch("cognisight.recognition.cli._run_service_command") as start,
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(
                    main(
                        [
                            "run",
                            "--config",
                            str(Path(directory) / "config.json"),
                            "--state-dir",
                            str(state),
                        ]
                    ),
                    2,
                )
            self.assertFalse(state.exists())
            start.assert_not_called()
