"""Opt-in native import checks; no devices, configuration or downloads are opened."""
import json
import math
import re
import subprocess
import sys

PROBES = {
    "picamera2_libcamera": ("picamera2", "libcamera"),
    "cv2_numpy": ("cv2", "numpy"),
    "vosk": ("vosk",),
    "piper": ("piper",),
    "sounddevice": ("sounddevice",),
    "flask": ("flask",),
    "flask_wtf": ("flask_wtf",),
    "waitress": ("waitress",),
}

# Child stdout/stderr are captured by the parent, never forwarded. The child
# publishes only a fixed envelope; native diagnostics or exceptions stay private.
_CHILD = r'''
import contextlib, importlib, json, re, sys
result = {"state": "passed", "error_type": None}
try:
    with open("/dev/null", "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        modules = {name: importlib.import_module(name) for name in sys.argv[1:]}
        if "cv2" in modules:
            from cognisight.recognition.vision import Vision
            if not Vision.supported_opencv(modules["cv2"].__version__):
                raise RuntimeError("Unsupported OpenCV")
            if not all(hasattr(modules["cv2"], name) for name in ("FaceDetectorYN", "FaceRecognizerSF")):
                raise RuntimeError("Missing face APIs")
except ModuleNotFoundError:
    result = {"state": "missing", "error_type": "ModuleNotFoundError"}
except Exception as exc:
    name = type(exc).__name__
    result = {"state": "failed", "error_type": name if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name) else "ImportError"}
print(json.dumps(result))
'''


def _probe(name, timeout_seconds):
    if name not in PROBES:
        raise ValueError("Unknown diagnostic probe")
    try:
        child = subprocess.run(
            [sys.executable, "-c", _CHILD, *PROBES[name]],
            capture_output=True, text=True, timeout=timeout_seconds, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"state": "timeout", "error_type": "TimeoutExpired"}
    if child.returncode != 0:
        return {"state": "failed", "error_type": "ChildProcessError"}
    try:
        result = json.loads(child.stdout)
        # Treat unexpected output as a failed probe, never copy it into reports.
        state, error = result["state"], result["error_type"]
        if state not in ("passed", "missing", "failed") or (
            error is not None and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", error)
        ):
            raise ValueError("Invalid probe response")
        return {"state": state, "error_type": error}
    except (ValueError, KeyError, TypeError):
        return {"state": "failed", "error_type": "InvalidProbeResponse"}


def native_report(timeout_seconds=10.0):
    """Probe each dependency in a child with its own bounded import timeout.

    Passing means imports and required OpenCV APIs work, never that a camera,
    sound adapter, model or receiver works. At most eight probes run in sequence.
    """
    if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 300:
        raise ValueError("Probe timeout must be finite and between 0 and 300 seconds")
    return {
        "schema_version": 1,
        "release_qualified": False,
        "dependencies": {name: _probe(name, timeout_seconds) for name in PROBES},
    }
