"""Vision contract tests; real inference requires optional libraries and models."""

import importlib.util
import tempfile
import threading
import time
import unittest
from pathlib import Path

from cognisight.recognition.vision import LatestFrame, Vision, geometry_reason


def face(x=100, y=100, width=100, height=100):
    return [
        x,
        y,
        width,
        height,
        x + 30,
        y + 35,
        x + 70,
        y + 35,
        x + 50,
        y + 55,
        x + 35,
        y + 80,
        x + 65,
        y + 80,
        0.99,
    ]


class GeometryTests(unittest.TestCase):
    def test_small_outside_and_sideways_faces_are_rejected(self):
        self.assertEqual(geometry_reason(face(), 640, 480), "")
        self.assertIn("closer", geometry_reason(face(width=40), 640, 480))
        self.assertIn("frame", geometry_reason(face(x=600), 640, 480))
        sideways = face()
        sideways[8] = 110
        self.assertIn("camera", geometry_reason(sideways, 640, 480))
        tilted = face()
        tilted[7] += 30
        self.assertIn("level", geometry_reason(tilted, 640, 480))

    def test_nonfinite_and_malformed_landmarks_fail_closed(self):
        for bad in ([], [1] * 14, [float("nan")] * 15, [float("inf")] * 15):
            self.assertTrue(geometry_reason(bad, 640, 480))


class LatestFrameTests(unittest.TestCase):
    def test_only_latest_frame_is_retained_and_no_duplicate_reads(self):
        slot = LatestFrame()
        slot.publish("old")
        slot.publish("new")
        self.assertEqual(slot.read(timeout=0.01), "new")
        with self.assertRaises(TimeoutError):
            slot.read(timeout=0.01)

    def test_capture_failure_wakes_waiter(self):
        slot = LatestFrame()
        slot.fail(RuntimeError("camera disconnected"))
        with self.assertRaisesRegex(RuntimeError, "capture failed"):
            slot.read(timeout=0.01)

    def test_closed_slot_wakes_waiter(self):
        slot = LatestFrame()
        slot.close()
        with self.assertRaisesRegex(RuntimeError, "closed"):
            slot.read(timeout=0.01)


class VisionStartupTests(unittest.TestCase):
    def test_dead_capture_reader_does_not_allow_replacing_open_camera(self):
        # Capture failure can end the reader while Picamera2 still owns hardware.
        vision = Vision({})
        camera = object()
        vision._camera = camera
        reader = threading.Thread(target=lambda: None)
        reader.start()
        reader.join()
        vision._reader = reader
        with self.assertRaisesRegex(RuntimeError, "close it before restarting"):
            vision.start()
        self.assertIs(vision._camera, camera)
        self.assertIs(vision._reader, reader)

    def test_missing_model_fails_before_hardware_import(self):
        with tempfile.TemporaryDirectory() as directory:
            v = Vision(
                {
                    "detector_model": str(Path(directory) / "missing.onnx"),
                    "recognizer_model": str(Path(directory) / "sface.onnx"),
                }
            )
            with self.assertRaisesRegex(FileNotFoundError, "model"):
                v.start()
            v.close()

    def test_version_gate_does_not_claim_incompatible_opencv_support(self):
        self.assertTrue(Vision.supported_opencv("4.10.0"))
        self.assertTrue(Vision.supported_opencv("4.13.0-dev"))
        for version in ("4.6.0", "5.0.0", "garbage"):
            self.assertFalse(Vision.supported_opencv(version))


@unittest.skipUnless(
    importlib.util.find_spec("numpy") and importlib.util.find_spec("cv2"),
    "numpy/OpenCV unavailable: image quality integration not run",
)
class ImageQualityTests(unittest.TestCase):
    def test_dark_bright_and_blurred_images_rejected(self):
        import cv2
        import numpy as np

        v = Vision({})
        v._cv2 = cv2
        v._np = np
        for pixels, reason in ((0, "lighting"), (255, "lighting"), (120, "blur")):
            image = np.full((480, 640, 3), pixels, dtype=np.uint8)
            self.assertIn(reason, v._quality_reason(image, face()))


if __name__ == "__main__":
    unittest.main()
