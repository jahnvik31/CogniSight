"""Camera input.

A Raspberry Pi camera on the CSI socket is opened with Picamera2. That is the
library that matches rpicam. OpenCV's VideoCapture is only the fallback for a
USB webcam or a laptop. Picamera2 comes from apt (`python3-picamera2`), and the
virtualenv has to be created with --system-site-packages to see it.

Picamera2's "RGB888" frames are B, G, R in memory (see the Picamera2
manual), the order OpenCV and DeepFace expect, so no conversion is done. If
faces look blue in the dashboard on a particular Pi, start with --swap-colors.
"""

from pathlib import Path


class Camera:
    def read(self):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError


class PiCamera(Camera):
    kind = "picamera2"

    def __init__(self, flip=False, swap_colors=False):
        from picamera2 import Picamera2

        info = Picamera2.global_camera_info()
        if not info:
            raise RuntimeError("Picamera2 found no camera on the CSI socket")
        camera = Picamera2()
        try:
            options = {}
            if flip:
                from libcamera import Transform

                options["transform"] = Transform(hflip=1, vflip=1)
            camera.configure(
                camera.create_video_configuration(
                    main={"size": (640, 480), "format": "RGB888"},
                    controls={"FrameRate": 15},
                    **options,
                )
            )
            camera.start()
        except Exception:
            camera.close()
            raise
        self._camera = camera
        self._swap = swap_colors
        model = camera.camera_properties.get("Model") if camera.camera_properties else None
        self.label = model or info[0].get("Model") or "Pi camera"

    def read(self):
        frame = self._camera.capture_array("main")
        if frame is None:
            raise RuntimeError("Pi camera returned no frame")
        if self._swap:
            frame = frame[:, :, ::-1].copy()
        return frame

    def save(self, path):
        self._camera.capture_file(str(path))

    def close(self):
        try:
            self._camera.stop()
        finally:
            self._camera.close()


class UsbCamera(Camera):
    kind = "usb"

    def __init__(self, index, flip=False):
        import cv2

        capture = cv2.VideoCapture(index)
        if not capture.isOpened():
            capture.release()
            raise RuntimeError("Could not open USB camera {}".format(index))
        self._capture = capture
        self._cv2 = cv2
        self._flip = flip
        self.label = "USB camera {}".format(index)

    def read(self):
        ok, frame = self._capture.read()
        if not ok or frame is None:
            raise RuntimeError("USB camera stopped returning frames")
        return self._cv2.flip(frame, -1) if self._flip else frame

    def save(self, path):
        frame = self.read()
        if not self._cv2.imwrite(str(path), frame):
            raise RuntimeError("Could not write {}".format(path))

    def close(self):
        self._capture.release()


def open_camera(index=0, flip=False, swap_colors=False):
    """Prefer the Pi CSI camera. Use a numbered webcam only when it is absent."""
    try:
        from picamera2 import Picamera2
    except ImportError:
        Picamera2 = None
    if Picamera2 is not None and Picamera2.global_camera_info():
        return PiCamera(flip, swap_colors)
    try:
        return UsbCamera(index, flip)
    except ImportError as exc:
        raise RuntimeError(
            "No Picamera2 camera was found, and OpenCV is not installed for a USB camera"
        ) from exc


def save_snapshot(path, index=0, flip=False):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    camera = open_camera(index, flip)
    try:
        camera.save(destination)
        frame = camera.read()
        height, width = frame.shape[:2]
        return camera.kind, camera.label, width, height, destination
    finally:
        camera.close()
