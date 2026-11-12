"""Setup and qualification tests using archives and anonymous trial fixtures."""

import importlib.util
import io
import contextlib
import csv
import os
import hashlib
import json
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import warnings
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fetch = load("fetch_models")
qualify = load("qualify")


class ArchiveTests(unittest.TestCase):
    def archive(self, entries):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for key, value in entries:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    archive.writestr(key, value)
        stream.seek(0)
        return stream

    def test_extracts_regular_model_files_and_hashes_every_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            files = fetch.safe_extract(
                self.archive(
                    [("model/conf/a.conf", b"hello"), ("model/am/a.mdl", b"world")]
                ),
                root,
            )
            self.assertEqual(
                sorted(p.relative_to(root).as_posix() for p in files),
                ["model/am/a.mdl", "model/conf/a.conf"],
            )
            self.assertEqual((root / "model/conf/a.conf").read_bytes(), b"hello")
            self.assertEqual(
                fetch.sha256(root / "model/conf/a.conf"),
                "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
            )

    def test_traversal_absolute_windows_and_links_are_rejected(self):
        link = zipfile.ZipInfo("model/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        for name in ("../escaped", "/absolute", "C:/windows", "model\\escape", link):
            with (
                self.subTest(name=str(name)),
                tempfile.TemporaryDirectory() as directory,
            ):
                with self.assertRaises(ValueError):
                    fetch.safe_extract(
                        self.archive([(name, b"target")]), Path(directory)
                    )

    def test_extraction_size_limit_and_duplicate_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                fetch.safe_extract(
                    self.archive([("model/large", b"12345")]),
                    Path(directory),
                    max_total=4,
                )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                fetch.safe_extract(
                    self.archive([("model/a", b"a"), ("model/a", b"b")]),
                    Path(directory),
                )

    def test_hosts_and_redirects_require_official_https(self):
        for url in (
            "http://alphacephei.com/model.zip",
            "https://evil.example/model",
            "https://api.github.com.evil.example/x",
            "file:///tmp/x",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                fetch.validate_url(url)
        for url in (
            "https://api.github.com/repos/opencv/opencv_zoo/commits/main",
            "https://huggingface.co/a",
            "https://cas-bridge.xethub.hf.co/a",
        ):
            fetch.validate_url(url)

    def test_lfs_pointer_parsing_rejects_unverified_payload(self):
        pointer = (
            b"version https://git-lfs.github.com/spec/v1\noid sha256:"
            + b"a" * 64
            + b"\nsize 1234\n"
        )
        self.assertEqual(fetch.lfs_oid(pointer), "a" * 64)
        with self.assertRaises(ValueError):
            fetch.lfs_oid(b"not a pointer")


class FetchPipelineTests(unittest.TestCase):
    def fixtures(self, broken=False):
        commit, revision = "a" * 40, "b" * 40
        responses = {
            "https://api.github.com/repos/opencv/opencv_zoo/commits/main": json.dumps(
                {"sha": commit}
            ).encode(),
        }
        for folder, name in (
            ("face_detection_yunet", "face_detection_yunet_2023mar.onnx"),
            ("face_recognition_sface", "face_recognition_sface_2021dec.onnx"),
        ):
            payload = ("fixture-model-" + name).encode()
            digest = hashlib.sha256(payload).hexdigest()
            remote = "models/" + folder + "/" + name
            responses[
                "https://raw.githubusercontent.com/opencv/opencv_zoo/"
                + commit
                + "/"
                + remote
            ] = (
                "version https://git-lfs.github.com/spec/v1\noid sha256:"
                + digest
                + "\nsize 1\n"
            ).encode()
            responses[
                "https://media.githubusercontent.com/media/opencv/opencv_zoo/"
                + commit
                + "/"
                + remote
            ] = (b"corrupt" if broken else payload)
        siblings = []
        for name in (
            "en_US-lessac-medium.onnx",
            "en_US-lessac-medium.onnx.json",
            "MODEL_CARD",
        ):
            payload = ("fixture-voice-" + name).encode()
            remote = fetch.PIPER_PREFIX + name
            siblings.append(
                {
                    "rfilename": remote,
                    "lfs": {"sha256": hashlib.sha256(payload).hexdigest()},
                }
            )
            responses[
                "https://huggingface.co/rhasspy/piper-voices/resolve/"
                + revision
                + "/"
                + remote
            ] = payload
        responses[
            "https://huggingface.co/api/models/rhasspy/piper-voices/revision/main?blobs=true"
        ] = json.dumps({"sha": revision, "siblings": siblings}).encode()
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr(
                "vosk-model-small-en-us-0.15/conf/model.conf", b"fixture configuration"
            )
        responses[fetch.VOSK_URL] = stream.getvalue()
        return responses

    def test_manifest_covers_extracted_assets_and_immutable_sources(self):
        responses = self.fixtures()
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "models"
            with patch.object(
                fetch, "request", side_effect=lambda url: io.BytesIO(responses[url])
            ):
                manifest = fetch.fetch(destination)
            self.assertTrue((destination / "manifest.json").is_file())
            self.assertEqual(len(manifest["files"]), 6)
            for item in manifest["files"]:
                self.assertEqual(
                    hashlib.sha256(
                        (destination / item["path"]).read_bytes()
                    ).hexdigest(),
                    item["sha256"],
                )
            self.assertTrue(manifest["model_version"].startswith("sface:"))
            self.assertEqual(manifest["sources"]["opencv"]["revision"], "a" * 40)
            with self.assertRaises(ValueError):
                fetch.fetch(destination)

    def test_checksum_mismatch_does_not_publish_partial_destination(self):
        responses = self.fixtures(broken=True)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "models"
            with patch.object(
                fetch, "request", side_effect=lambda url: io.BytesIO(responses[url])
            ):
                with self.assertRaises(ValueError):
                    fetch.fetch(destination)
            self.assertFalse(destination.exists())


class QualificationTests(unittest.TestCase):
    def test_percentile_empty_and_nonfinite_latency(self):
        self.assertIsNone(qualify.percentile([], 0.95))
        self.assertEqual(qualify.percentile([10, 20, 30, 40, 50], 0.95), 50)
        with self.assertRaises(ValueError):
            qualify.evaluate_trials(
                [
                    {
                        "kind": "recognition",
                        "encounter_id": "1",
                        "correct": "1",
                        "latency_ms": "nan",
                    }
                ]
            )

    def test_duplicate_encounters_do_not_inflate_unknown_evidence(self):
        rows = [
            {
                "kind": "unknown",
                "encounter_id": "same",
                "correct": "1",
                "latency_ms": "",
            }
        ] * 300
        result = qualify.evaluate_trials(rows)
        self.assertEqual(result["unknown"]["count"], 1)
        self.assertFalse(result["unknown"]["acceptance_passed"])

    def test_contradictory_duplicate_is_rejected(self):
        rows = [
            {"kind": "unknown", "encounter_id": "same", "correct": c, "latency_ms": ""}
            for c in ("1", "0")
        ]
        with self.assertRaises(ValueError):
            qualify.evaluate_trials(rows)

    def test_false_accept_fails_even_with_three_hundred_trials(self):
        rows = [
            {
                "kind": "unknown",
                "encounter_id": str(i),
                "correct": "0" if i == 3 else "1",
                "latency_ms": "",
            }
            for i in range(300)
        ]
        report = qualify.evaluate_trials(rows)
        self.assertEqual(report["unknown"]["false_named_announcements"], 1)
        self.assertFalse(report["unknown"]["acceptance_passed"])

    def test_all_unknown_trials_pass_only_as_observed_test_evidence(self):
        rows = [
            {
                "kind": "unknown",
                "encounter_id": str(i),
                "correct": "1",
                "latency_ms": "",
            }
            for i in range(300)
        ]
        report = qualify.evaluate_trials(rows)
        self.assertTrue(report["unknown"]["acceptance_passed"])
        self.assertGreater(report["unknown"]["false_accept_upper_95"], 0)
        self.assertFalse(report["release_qualified"])

    def test_command_coverage_requires_each_intent_per_speaker(self):
        rows = [
            {
                "kind": "command",
                "encounter_id": str(i),
                "correct": "1",
                "latency_ms": "500",
                "intent": "identify",
                "speaker_id": "s1",
            }
            for i in range(140)
        ]
        report = qualify.evaluate_trials(rows)
        self.assertFalse(report["command"]["acceptance_passed"])
        self.assertNotIn("s1", json.dumps(report))

    def test_metadata_excludes_serial_and_personal_host_identifiers(self):
        report = qualify.hardware_report()
        self.assertIn("acceptance", report)
        self.assertFalse(report["release_qualified"])
        self.assertNotIn("hostname", report)
        self.assertNotIn("serial", report)


class QualificationGateRegressionTests(unittest.TestCase):
    def stop_trials(self, count=20):
        return [
            {
                "kind": "stop",
                "encounter_id": str(index),
                "correct": "1",
                "latency_ms": "500",
            }
            for index in range(count)
        ]

    def command_trials(self, speaker, samples=20):
        return [
            {
                "kind": "command",
                "encounter_id": f"{speaker}-{intent}-{index}",
                "correct": "1",
                "latency_ms": "500",
                "speaker_id": speaker,
                "intent": intent,
            }
            for intent in qualify.INTENTS
            for index in range(samples)
        ]

    def test_every_stop_trial_must_meet_deadline_not_just_percentile(self):
        rows = self.stop_trials()
        rows[-1]["latency_ms"] = "1001"
        result = qualify.evaluate_trials(rows)["stop"]
        self.assertEqual(result["p95_latency_ms"], 500)
        self.assertFalse(result["acceptance_passed"])
        self.assertEqual(result["max_latency_ms"], 1001)

    def test_every_stop_trial_must_succeed(self):
        rows = self.stop_trials()
        rows[-1]["correct"] = "0"
        self.assertFalse(qualify.evaluate_trials(rows)["stop"]["acceptance_passed"])
        self.assertTrue(
            qualify.evaluate_trials(self.stop_trials(1))["stop"]["acceptance_passed"]
        )
        self.assertFalse(qualify.evaluate_trials([])["stop"]["acceptance_passed"])

    def test_command_accuracy_cannot_hide_one_bad_intent(self):
        rows = self.command_trials("speaker-private-id")
        rows[0]["correct"] = rows[1]["correct"] = "0"
        result = qualify.evaluate_trials(rows)["command"]
        self.assertGreater(result["accuracy"], 0.95)
        self.assertFalse(result["acceptance_passed"])
        self.assertEqual(result["intent_groups_failed"], 1)
        self.assertNotIn("speaker-private-id", json.dumps(result))

    def test_command_accuracy_cannot_hide_one_bad_speaker(self):
        rows = self.command_trials("wearer-private-id")
        for index, row in enumerate(rows):
            if index % 20 < 2:
                row["correct"] = "0"
        rows += self.command_trials("other-private-id", samples=200)
        result = qualify.evaluate_trials(rows)["command"]
        self.assertGreater(result["accuracy"], 0.95)
        self.assertFalse(result["acceptance_passed"])
        self.assertEqual(result["speaker_groups_failed"], 1)
        self.assertNotIn("wearer-private-id", json.dumps(result))
        self.assertNotIn("other-private-id", json.dumps(result))

    def test_command_gate_rejects_a_bad_speaker_intent_cell(self):
        rows = self.command_trials("wearer-a") + self.command_trials("wearer-b")
        rows[0]["correct"] = rows[1]["correct"] = "0"
        result = qualify.evaluate_trials(rows)["command"]
        self.assertFalse(result["acceptance_passed"])
        self.assertEqual(result["speaker_intent_groups_failed"], 1)
        good = qualify.evaluate_trials(self.command_trials("wearer-a"))["command"]
        self.assertTrue(good["acceptance_passed"])


class QualificationReportRegressionTests(unittest.TestCase):
    def test_failed_audio_smoke_is_nonzero_with_reported_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            smoke = {
                "camera_inference": {"state": "smoke_passed"},
                "audio": {"state": "failed"},
            }
            with (
                patch.object(qualify, "smoke", return_value=smoke),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                result = qualify.main(
                    [
                        "--config",
                        str(Path(directory) / "config.json"),
                        "--output",
                        str(output),
                    ]
                )
            self.assertNotEqual(result, 0)
            report = json.loads(output.read_text())
            self.assertEqual(report["smoke"]["audio"]["state"], "failed")
            self.assertFalse(report["release_qualified"])

    def test_report_is_atomic_private_and_replaces_only_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            qualify.write_report(output, {"state": "pending"})
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            with self.assertRaises(ValueError):
                qualify.write_report(output, {"measurement": float("nan")})
            self.assertEqual(json.loads(output.read_text()), {"state": "pending"})
            self.assertEqual(list(Path(directory).iterdir()), [output])

    def test_report_rejects_symlink_without_touching_link_target(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"
            source.write_text("private source")
            output = Path(directory) / "report.json"
            output.symlink_to(source)
            with self.assertRaises(ValueError):
                qualify.write_report(output, {"state": "pending"})
            self.assertTrue(output.is_symlink())
            self.assertEqual(source.read_text(), "private source")

    def test_report_cannot_overwrite_config_trials_or_hardlink_alias(self):
        for option in ("--config", "--trials"):
            for hardlink in (False, True):
                with (
                    self.subTest(option=option, hardlink=hardlink),
                    tempfile.TemporaryDirectory() as directory,
                ):
                    source = Path(directory) / "source"
                    source.write_text("original private source")
                    output = Path(directory) / "report.json" if hardlink else source
                    if hardlink:
                        os.link(source, output)
                    with (
                        patch.object(
                            qualify,
                            "smoke",
                            return_value={
                                "camera_inference": {"state": "smoke_passed"},
                                "audio": {"state": "pending_interactive_check"},
                            },
                        ) as smoke,
                        contextlib.redirect_stdout(io.StringIO()),
                        contextlib.redirect_stderr(io.StringIO()),
                    ):
                        result = qualify.main(
                            [option, str(source), "--output", str(output)]
                        )
                    self.assertNotEqual(result, 0)
                    self.assertEqual(source.read_text(), "original private source")
                    self.assertEqual(output.read_text(), "original private source")
                    smoke.assert_not_called()


class TrialExitStatusTests(unittest.TestCase):
    def run_trials(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "trials.csv"
            report_path = Path(directory) / "report.json"
            with source.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=(
                    "kind", "encounter_id", "correct", "latency_ms", "intent", "speaker_id"
                ))
                writer.writeheader()
                writer.writerows(rows)
            before = source.read_bytes()
            with contextlib.redirect_stdout(io.StringIO()):
                code = qualify.main(["--trials", str(source), "--output", str(report_path)])
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(stat.S_IMODE(report_path.stat().st_mode), 0o600)
            return code, json.loads(report_path.read_text())

    def unknown_trials(self):
        return [{"kind": "unknown", "encounter_id": str(i), "correct": "1"}
                for i in range(300)]

    def test_valid_csv_with_failed_measurements_exits_one_and_keeps_private_report(self):
        rows = self.unknown_trials()
        rows[-1]["correct"] = "0"
        code, report = self.run_trials(rows)
        self.assertEqual(code, 1)
        self.assertFalse(report["trials"]["unknown"]["acceptance_passed"])
        self.assertEqual(report["trials"]["unknown"]["false_named_announcements"], 1)
        self.assertFalse(report["release_qualified"])

    def test_passed_supplied_category_does_not_require_unmeasured_categories(self):
        code, report = self.run_trials(self.unknown_trials())
        self.assertEqual(code, 0)
        self.assertTrue(report["trials"]["unknown"]["acceptance_passed"])
        self.assertEqual(report["trials"]["recognition"]["count"], 0)
        self.assertEqual(report["acceptance"]["held_out_accuracy"], "pending")
        self.assertFalse(report["release_qualified"])

    def test_empty_requested_trials_fail_instead_of_successful_no_evidence(self):
        code, report = self.run_trials([])
        self.assertEqual(code, 1)
        self.assertEqual(report["trials"]["unknown"]["count"], 0)


class MeasuredSmokeTests(unittest.TestCase):
    def fake_vision(self, faces=0, fail=False):
        from types import SimpleNamespace
        class Camera:
            camera_properties = {'Model': 'imx219', 'SerialNumber': 'PRIVATE'}
        class FakeVision:
            closed = False
            _cv2 = SimpleNamespace(__version__='4.10.0')
            _np = SimpleNamespace(__version__='1.26.4')
            _camera = Camera()
            def __init__(self, config):
                pass
            def start(self):
                if fail:
                    raise RuntimeError('PRIVATE')
            def read(self):
                return SimpleNamespace(image=object())
            def detect(self, image):
                return [object()] * faces
            def close(self):
                FakeVision.closed = True
        return FakeVision

    def run_smoke(self, faces=0, fail=False, seconds=1):
        vision = self.fake_vision(faces, fail)
        with patch('cognisight.recognition.config.load_config', return_value={}), patch('cognisight.recognition.vision.Vision', vision), patch.object(qualify.time, 'monotonic', side_effect=[0, 0, .1, .2, 2, 2]):
            result = qualify.smoke('synthetic.json', seconds)
        self.assertTrue(vision.closed)
        return result

    def test_empty_scene_measures_detector_but_not_recognizer_features(self):
        result = self.run_smoke()
        self.assertEqual(result['camera_inference']['state'], 'smoke_passed')
        self.assertEqual(result['camera_inference']['recognizer_features'], 'pending')
        self.assertEqual(result['camera_inference']['sensor_model'], 'imx219')
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_observed_features_measure_execution_not_identity_accuracy(self):
        result = self.run_smoke(faces=1)
        self.assertEqual(result['camera_inference']['recognizer_features'], 'smoke_passed')
        self.assertEqual(result['camera_inference']['frames'], 1)
        self.assertEqual(result['camera_inference']['imported_versions']['cv2'], '4.10.0')

    def test_zero_frames_fail_and_normal_camera_failure_cleans_up(self):
        self.assertEqual(self.run_smoke(seconds=0)['camera_inference']['state'], 'failed')
        result = self.run_smoke(fail=True)
        self.assertEqual(result['camera_inference']['state'], 'failed')
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_audio_python_failure_keeps_camera_evidence_and_sanitizes_report(self):
        class BrokenAudio:
            closed = False
            def __init__(self, *args):
                pass
            def start(self):
                raise RuntimeError('PRIVATE')
            def close(self):
                BrokenAudio.closed = True
        with patch('cognisight.recognition.config.load_config', return_value={}), patch('cognisight.recognition.vision.Vision', self.fake_vision()), patch('cognisight.recognition.audio.AudioEngine', BrokenAudio), patch.object(qualify.sys.stdin, 'isatty', return_value=True), patch.object(qualify.time, 'monotonic', side_effect=[0, 0, .1, .2, 2, 2]):
            result = qualify.smoke('synthetic.json', 1, interactive=True)
        self.assertEqual(result['camera_inference']['state'], 'smoke_passed')
        self.assertEqual(result['audio']['state'], 'failed')
        self.assertTrue(BrokenAudio.closed)
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_empty_scene_keeps_recognition_pending_and_inventory_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / 'inventory.json'
            output = Path(directory) / 'smoke.json'
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(qualify.main(['--output', str(inventory)]), 0)
            original = inventory.read_bytes()
            with patch.object(qualify, 'smoke', return_value={'camera_inference': {'state': 'smoke_passed', 'recognizer_features': 'pending'}, 'audio': {'state': 'pending_interactive_check'}}), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(qualify.main(['--config', 'synthetic.json', '--output', str(output)]), 0)
            self.assertEqual(json.loads(output.read_text())['acceptance']['recognition_inference'], 'pending')
            with patch.object(qualify, 'smoke', side_effect=RuntimeError('PRIVATE')), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(qualify.main(['--config', 'synthetic.json', '--output', str(output)]), 1)
            self.assertEqual(inventory.read_bytes(), original)
            self.assertNotIn('PRIVATE', output.read_text())


if __name__ == "__main__":
    unittest.main()
