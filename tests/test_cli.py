import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
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
                        ["run", "--config", str(config), "--state-dir", str(Path(root) / "private")]
                    ),
                    2,
                )
            self.assertFalse((Path(root) / "private").exists())

    def test_password_rejects_repo_state_before_prompt_or_write(self):
        from unittest.mock import patch
        from cognisight.recognition.cli import validate_state_dir

        with self.assertRaises(ValueError):
            validate_state_dir(Path(__file__).resolve().parents[1] / "private-data")
