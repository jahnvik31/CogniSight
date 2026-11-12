import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from cognisight.recognition.config import load_config
from cognisight.recognition.store import Store
from cognisight.recognition.matching import Gallery


class IntegrityTests(unittest.TestCase):
    def test_model_manifest_detects_tampering_and_unlisted_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            models = root / "models"
            (models / "speech/am").mkdir(parents=True)
            names = (
                "detect.onnx",
                "recognize.onnx",
                "voice.onnx",
                "voice.onnx.json",
                "speech/am/final.mdl",
            )
            for name in names:
                (models / name).write_bytes(name.encode())
            files = [
                {"path": name, "sha256": hashlib.sha256(name.encode()).hexdigest()}
                for name in names
            ]
            (models / "manifest.json").write_text(json.dumps({"files": files}))
            config = dict(
                model_version="sface:" + hashlib.sha256(b"recognize.onnx").hexdigest(),
                threshold=0.6,
                margin=0.08,
                calibrated=False,
                input_device="USB Mic",
                output_device="USB Headset",
                detector_model="models/detect.onnx",
                recognizer_model="models/recognize.onnx",
                piper_model="models/voice.onnx",
                vosk_model="models/speech",
                manifest="models/manifest.json",
            )
            (root / "config.json").write_text(json.dumps(config))
            self.assertEqual(load_config(root / "config.json")["threshold"], 0.6)
            (models / "speech/unlisted").write_bytes(b"not verified")
            with self.assertRaises(ValueError):
                load_config(root / "config.json")
            (models / "speech/unlisted").unlink()
            (models / "detect.onnx").write_bytes(b"changed")
            with self.assertRaises(ValueError):
                load_config(root / "config.json")

    def test_hundred_profile_capacity_and_gallery_matching(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "db")
            try:
                ids = []
                for i in range(100):
                    vector = [int(j == i) for j in range(100)]
                    ids.append(
                        store.enroll("Person " + str(i), "", "", "", [vector] * 10, "test-only")
                    )
                gallery = Gallery(store.gallery("test-only"), 0.8, 0.1)
                self.assertEqual(
                    gallery.match([int(j == 99) for j in range(100)]).person_id, ids[-1]
                )
                with self.assertRaises(ValueError):
                    store.enroll("One too many", "", "", "", [[1, 0]] * 10, "test-only")
            finally:
                store.close()
