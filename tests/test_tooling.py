"""Setup and qualification tests using archives and anonymous trial fixtures."""

import importlib.util
import io
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
                self.archive([("model/conf/a.conf", b"hello"), ("model/am/a.mdl", b"world")]), root
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
            with self.subTest(name=str(name)), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    fetch.safe_extract(self.archive([(name, b"target")]), Path(directory))

    def test_extraction_size_limit_and_duplicate_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                fetch.safe_extract(
                    self.archive([("model/large", b"12345")]), Path(directory), max_total=4
                )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                fetch.safe_extract(
                    self.archive([("model/a", b"a"), ("model/a", b"b")]), Path(directory)
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
                "https://raw.githubusercontent.com/opencv/opencv_zoo/" + commit + "/" + remote
            ] = (
                "version https://git-lfs.github.com/spec/v1\noid sha256:" + digest + "\nsize 1\n"
            ).encode()
            responses[
                "https://media.githubusercontent.com/media/opencv/opencv_zoo/"
                + commit
                + "/"
                + remote
            ] = (b"corrupt" if broken else payload)
        siblings = []
        for name in ("en_US-lessac-medium.onnx", "en_US-lessac-medium.onnx.json", "MODEL_CARD"):
            payload = ("fixture-voice-" + name).encode()
            remote = fetch.PIPER_PREFIX + name
            siblings.append(
                {"rfilename": remote, "lfs": {"sha256": hashlib.sha256(payload).hexdigest()}}
            )
            responses[
                "https://huggingface.co/rhasspy/piper-voices/resolve/" + revision + "/" + remote
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
            with patch.object(fetch, "request", side_effect=lambda url: io.BytesIO(responses[url])):
                manifest = fetch.fetch(destination)
            self.assertTrue((destination / "manifest.json").is_file())
            self.assertEqual(len(manifest["files"]), 6)
            for item in manifest["files"]:
                self.assertEqual(
                    hashlib.sha256((destination / item["path"]).read_bytes()).hexdigest(),
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
            with patch.object(fetch, "request", side_effect=lambda url: io.BytesIO(responses[url])):
                with self.assertRaises(ValueError):
                    fetch.fetch(destination)
            self.assertFalse(destination.exists())


class QualificationTests(unittest.TestCase):
    def test_percentile_empty_and_nonfinite_latency(self):
        self.assertIsNone(qualify.percentile([], 0.95))
        self.assertEqual(qualify.percentile([10, 20, 30, 40, 50], 0.95), 50)
        with self.assertRaises(ValueError):
            qualify.evaluate_trials(
                [{"kind": "recognition", "encounter_id": "1", "correct": "1", "latency_ms": "nan"}]
            )

    def test_duplicate_encounters_do_not_inflate_unknown_evidence(self):
        rows = [{"kind": "unknown", "encounter_id": "same", "correct": "1", "latency_ms": ""}] * 300
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
            {"kind": "unknown", "encounter_id": str(i), "correct": "1", "latency_ms": ""}
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


if __name__ == "__main__":
    unittest.main()
