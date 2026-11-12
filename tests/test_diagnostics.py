"""Native diagnostics never acquire hardware or publish child output."""
import contextlib
import io
import json
import subprocess
import unittest
from unittest.mock import patch

from cognisight.recognition import diagnostics
from cognisight.recognition.cli import main


class DiagnosticsTests(unittest.TestCase):
    def test_probe_classifies_missing_error_exit_and_timeout_without_private_output(self):
        outcomes = [
            subprocess.CompletedProcess([], 0, '{"state":"missing","error_type":"ModuleNotFoundError"}', 'PRIVATE'),
            subprocess.CompletedProcess([], 0, '{"state":"failed","error_type":"ImportError"}', 'PRIVATE'),
            subprocess.CompletedProcess([], -11, 'PRIVATE', 'PRIVATE'),
            subprocess.TimeoutExpired('probe', 0.1, output='PRIVATE', stderr='PRIVATE'),
        ]
        with patch.object(diagnostics.subprocess, 'run', side_effect=outcomes):
            entries = [diagnostics._probe('cv2_numpy', 0.1) for _ in outcomes]
        self.assertEqual([entry['state'] for entry in entries], ['missing', 'failed', 'failed', 'timeout'])
        self.assertNotIn('PRIVATE', json.dumps(entries))

    def test_report_all_required_probes_and_success_is_not_hardware_qualification(self):
        with patch.object(diagnostics, '_probe', return_value={'state': 'passed', 'error_type': None}) as probe:
            report = diagnostics.native_report()
        self.assertFalse(report['release_qualified'])
        self.assertEqual(report['schema_version'], 1)
        self.assertEqual(probe.call_count, 8)
        self.assertEqual(set(report['dependencies']), set(diagnostics.PROBES))

    def test_invalid_timeout_rejected_and_probe_names_fixed(self):
        for timeout in (0, -1, float('nan'), float('inf'), 301):
            with self.assertRaises(ValueError):
                diagnostics.native_report(timeout)
        with self.assertRaises(ValueError):
            diagnostics._probe('PRIVATE', 1)

    def test_native_cli_exit_status_and_plain_doctor_does_not_probe(self):
        for state, expected in [('passed', 0), ('missing', 1), ('failed', 1), ('timeout', 1)]:
            with patch.object(diagnostics, 'native_report', return_value={'dependencies': {'test': {'state': state}}, 'release_qualified': False}), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(['doctor', '--native']), expected)
                self.assertNotIn('PRIVATE', output.getvalue())
        with patch.object(diagnostics, 'native_report') as native, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['doctor']), 0)
            native.assert_not_called()

    def test_real_child_missing_import_sanitized(self):
        # Run the actual child code against a fabricated module, without a device.
        import os
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'vosk.py').write_text('print("PRIVATE"); raise ImportError("PRIVATE")')
            environment = dict(os.environ, PYTHONPATH=directory)
            with patch.dict(os.environ, environment, clear=True):
                result = diagnostics._probe('vosk', 2)
        self.assertEqual(result, {'state': 'failed', 'error_type': 'ImportError'})

    def test_actual_children_timeout_abnormal_exit_and_supported_vision_policy(self):
        import os
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory, 'vosk.py')
            with patch.dict(os.environ, {'PYTHONPATH': directory + os.pathsep + str(Path(__file__).resolve().parents[1] / 'src')}):
                fake.write_text('import time; time.sleep(5)')
                self.assertEqual(diagnostics._probe('vosk', .1)['state'], 'timeout')
                fake.write_text('import os; os._exit(7)')
                self.assertEqual(diagnostics._probe('vosk', 2)['error_type'], 'ChildProcessError')
                Path(directory, 'numpy.py').write_text('__version__ = "1.26.4"')
                cv2 = Path(directory, 'cv2.py')
                cv2.write_text('__version__ = "4.9.0"\nFaceDetectorYN = object()\nFaceRecognizerSF = object()')
                self.assertEqual(diagnostics._probe('cv2_numpy', 2)['state'], 'failed')
                cv2.write_text('__version__ = "4.10.0"\nFaceDetectorYN = object()\nFaceRecognizerSF = object()')
                self.assertEqual(diagnostics._probe('cv2_numpy', 2)['state'], 'passed')


class NativeOutputBoundaryTests(unittest.TestCase):
    def test_non_utf8_child_response_fails_without_aborting_report(self):
        result = subprocess.CompletedProcess([], 0, b"\xffPRIVATE", b"\xfePRIVATE")
        with patch.object(diagnostics.subprocess, "run", return_value=result):
            self.assertEqual(diagnostics._probe("vosk", 1),
                             {"state": "failed", "error_type": "InvalidProbeResponse"})

    def test_native_file_descriptor_output_is_discarded_without_breaking_probe(self):
        import os
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "vosk.py").write_text(
                "import os; os.write(1, b'\\xffPRIVATE'); os.write(2, b'\\xfePRIVATE')"
            )
            with patch.dict(os.environ, {"PYTHONPATH": directory}):
                self.assertEqual(diagnostics._probe("vosk", 2),
                                 {"state": "passed", "error_type": None})

    def test_oversized_child_envelope_is_rejected(self):
        result = subprocess.CompletedProcess([], 0, b" " * 5000 +
                                             b'{"state":"passed","error_type":null}', b"")
        with patch.object(diagnostics.subprocess, "run", return_value=result):
            self.assertEqual(diagnostics._probe("vosk", 1),
                             {"state": "failed", "error_type": "InvalidProbeResponse"})
