"""Picamera2/OpenCV adapter. Optional native libraries are imported at startup.

Picamera2 RGB888 arrays have B,G,R byte order, matching OpenCV. See the
Raspberry Pi request.py FORMAT_TABLE (RGB888 -> BGR); do not swap channels.
No camera images are written to disk by this adapter.
"""

from __future__ import annotations

import math
import re
import threading
import time
from pathlib import Path
from typing import Any, Optional


def geometry_reason(face, width: int, height: int, minimum_size: int = 80) -> str:
    """Conservative crop/pose gate; empty string means geometrically usable.

    This is not a calibrated pose estimator, liveness test, or accuracy claim.
    YuNet coordinates: box, right eye, left eye, nose, mouth corners, score.
    """
    try:
        if len(face) < 15 or not all(math.isfinite(float(v)) for v in face):
            return "Invalid face landmarks."
        x, y, w, h = (float(v) for v in face[:4])
        if min(w, h) < minimum_size:
            return "Move closer to the camera."
        if x < 0 or y < 0 or x + w > width or y + h > height:
            return "Keep your whole face inside the frame."
        ex1, ey1, ex2, ey2, nx, ny = (float(v) for v in face[4:10])
        eye_distance = abs(ex2 - ex1)
        if eye_distance < 0.15 * w:
            return "Face the camera more directly."
        if abs(ey2 - ey1) > 0.3 * eye_distance:
            return "Keep your head level."
        nose_fraction = (nx - min(ex1, ex2)) / eye_distance
        if not 0.15 <= nose_fraction <= 0.85 or not y < ny < y + h:
            return "Face the camera more directly."
        if not y < ey1 < y + h or not y < ey2 < y + h:
            return "Invalid face landmarks."
        if not x < ex1 < x + w or not x < ex2 < x + w:
            return "Invalid face landmarks."
        return ""
    except (TypeError, ValueError, OverflowError):
        return "Invalid face landmarks."


class LatestFrame:
    """A bounded single-slot mailbox with consuming reads and failure wakeup."""

    def __init__(self):
        self._condition = threading.Condition()
        self._value = None
        self._version = 0
        self._read_version = 0
        self._error: Optional[BaseException] = None
        self._closed = False

    def publish(self, value):
        with self._condition:
            if self._closed or self._error is not None:
                return
            self._value = value
            self._version += 1
            self._condition.notify_all()

    def fail(self, error: BaseException):
        with self._condition:
            self._error = error
            self._value = None
            self._condition.notify_all()

    def close(self):
        with self._condition:
            self._closed = True
            self._value = None
            self._condition.notify_all()

    def read(self, timeout: float = 2.0):
        deadline = time.monotonic() + min(2.0, max(0.0, timeout))
        with self._condition:
            while True:
                if self._error is not None:
                    raise RuntimeError("Camera capture failed; recheck hardware.") from self._error
                if self._closed:
                    raise RuntimeError("Camera is closed.")
                if self._version != self._read_version:
                    self._read_version = self._version
                    return self._value
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("No new camera frame within two seconds.")
                self._condition.wait(remaining)


class Vision:
    """One camera owner, latest-frame capture, quality gates, YuNet and SFace.

    Public calls must be serialized by the runtime (OpenCV model objects are not
    shared across inference threads). The background thread only captures frames.
    After a capture error, close() and start() are required for an explicit retry.
    """

    def __init__(self, config: dict):
        self.config = config
        self._camera = None
        self._reader: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._slot = LatestFrame()
        self._cv2 = None
        self._np = None
        self._detector = None
        self._recognizer = None
        self._counter = 0

    @staticmethod
    def supported_opencv(version: str) -> bool:
        match = re.match(r"^(\d+)\.(\d+)", version)
        return bool(match and int(match[1]) == 4 and int(match[2]) >= 10)

    def start(self):
        if self._camera is not None or (
            self._reader is not None and self._reader.is_alive()
        ):
            # Reader failure does not release Picamera2's device ownership.
            # A retry must close that owner before creating another instance.
            raise RuntimeError("Camera owner already exists; close it before restarting.")
        paths = []
        for key in ("detector_model", "recognizer_model"):
            value = self.config.get(key)
            if not value or not Path(value).is_file():
                raise FileNotFoundError("Missing {} model; run explicit model setup.".format(key))
            paths.append(str(value))
        try:
            import cv2
            import numpy as np
            from picamera2 import Picamera2
        except ImportError as exc:
            raise RuntimeError("Install vision dependencies and apt python3-picamera2.") from exc
        if not self.supported_opencv(cv2.__version__):
            raise RuntimeError("OpenCV >=4.10,<5 is required for the selected model pair.")
        self._cv2, self._np = cv2, np
        cv2.setNumThreads(2)
        self._detector = cv2.FaceDetectorYN.create(paths[0], "", (640, 480), 0.9, 0.3, 5000)
        self._recognizer = cv2.FaceRecognizerSF.create(paths[1], "")
        camera = Picamera2()
        try:
            # RGB888 is BGR in host memory (libcamera packed-format naming).
            camera.configure(
                camera.create_video_configuration(
                    main={"size": (640, 480), "format": "RGB888"},
                    controls={"FrameRate": 15},
                    buffer_count=4,
                )
            )
            camera.start()
        except Exception:
            camera.close()
            raise
        self._camera = camera
        self._stop.clear()
        self._slot = LatestFrame()
        self._reader = threading.Thread(
            target=self._capture_loop, name="camera-capture", daemon=True
        )
        self._reader.start()

    def _capture_loop(self):
        from .types import FramePacket, clock_utc

        try:
            while not self._stop.is_set():
                image = self._camera.capture_array("main")
                captured_at = time.monotonic()
                if self._stop.is_set():
                    break
                if image is None or image.ndim != 3 or image.shape[2] != 3:
                    raise RuntimeError("Camera returned an invalid BGR frame.")
                self._counter += 1
                # Copy to own the buffer after libcamera releases its request.
                self._slot.publish(
                    FramePacket(self._counter, captured_at, clock_utc(), image.copy())
                )
        except Exception as exc:
            if not self._stop.is_set():
                self._slot.fail(exc)

    def read(self):
        packet = self._slot.read()
        if time.monotonic() - packet.captured_at > 2:
            raise TimeoutError("Camera frame is stale.")
        return packet

    def close(self):
        self._stop.set()
        self._slot.close()
        camera = self._camera
        if camera is not None:
            try:
                camera.stop()
            finally:
                camera.close()
        if self._reader is not None:
            self._reader.join(timeout=2)
            if self._reader.is_alive():
                # Refuse restart instead of opening a second camera owner.
                raise RuntimeError("Camera reader failed to stop; restart the service.")
        self._camera = None
        self._reader = None

    def _faces(self, image):
        if self._detector is None:
            raise RuntimeError("Vision models are not initialized.")
        if image is None or image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("Expected a three-channel BGR image.")
        height, width = image.shape[:2]
        self._detector.setInputSize((width, height))
        _, faces = self._detector.detect(image)
        return [] if faces is None else list(faces)

    def _quality_reason(self, image, face, enrollment: bool = True) -> str:
        height, width = image.shape[:2]
        reason = geometry_reason(face, width, height, 80 if enrollment else 60)
        if reason:
            return reason
        x, y, w, h = (int(v) for v in face[:4])
        roi = image[y : y + h, x : x + w]
        if roi.size == 0:
            return "Keep your whole face inside the frame."
        gray = self._cv2.cvtColor(roi, self._cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        if not 25 <= brightness <= 235:
            return "Improve the lighting on your face."
        blur = float(self._cv2.Laplacian(gray, self._cv2.CV_64F).var())
        if blur < (60 if enrollment else 40):
            return "Image is blurred; hold still and check focus."
        return ""

    def _embedding(self, image, face):
        aligned = self._recognizer.alignCrop(image, face)
        feature = self._recognizer.feature(aligned).reshape(-1)
        norm = float(self._np.linalg.norm(feature))
        if not math.isfinite(norm) or norm <= 0:
            raise ValueError("Face model produced an invalid embedding.")
        values = feature / norm
        if not self._np.isfinite(values).all():
            raise ValueError("Face model produced an invalid embedding.")
        return tuple(float(x) for x in values)

    def detect(self, image):
        faces = self._faces(image)
        # Bounded work: the four largest faces, ordered consistently by area.
        faces.sort(key=lambda f: float(f[2]) * float(f[3]), reverse=True)
        results = []
        for face in faces[:4]:
            if self._quality_reason(image, face, enrollment=False):
                continue
            try:
                embedding = self._embedding(image, face)
            except ValueError:
                continue
            results.append((tuple(int(v) for v in face[:4]), embedding))
        return results

    def enrollment_sample(self, image):
        faces = self._faces(image)
        if not faces:
            return None, "No face detected; face the camera."
        if len(faces) != 1:
            return None, "Only the person being enrolled may be in view."
        reason = self._quality_reason(image, faces[0])
        if reason:
            return None, reason
        try:
            return self._embedding(image, faces[0]), ""
        except ValueError:
            return None, "Unable to extract a usable face sample; try again."
