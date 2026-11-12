"""Explicit device/model configuration; no runtime downloads."""

import hashlib
import json
import math
from pathlib import Path


def validate_config(config):
    config = dict(config)
    for key in ("threshold", "margin"):
        value = config.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 < value <= 1
        ):
            raise ValueError("A finite positive " + key + " is required")
    if type(config.get("calibrated", False)) is not bool:
        raise ValueError("calibrated must be a boolean")
    for key in ("input_device", "output_device"):
        if not isinstance(config.get(key), str) or "usb" not in config[key].lower():
            raise ValueError(key + " must explicitly identify the USB device")
    if not config.get("model_version"):
        raise ValueError("model_version is required")
    config.setdefault("command_prefix", "computer")
    return config


def load_config(path, verify=True):
    path = Path(path).resolve()
    config = validate_config(json.loads(path.read_text()))
    for key in ("detector_model", "recognizer_model", "vosk_model", "piper_model"):
        value = Path(config[key]).expanduser()
        config[key] = str(value if value.is_absolute() else path.parent / value)
    if verify:
        manifest_path = Path(config.get("manifest", "models/manifest.json"))
        if not manifest_path.is_absolute():
            manifest_path = path.parent / manifest_path
        manifest = json.loads(manifest_path.read_text())
        for item in manifest["files"]:
            asset = manifest_path.parent / item["path"]
            if not asset.resolve().is_relative_to(manifest_path.parent.resolve()):
                raise ValueError("Asset path escapes model directory")
            digest = hashlib.sha256(asset.read_bytes()).hexdigest()
            if digest != item["sha256"]:
                raise ValueError("Model integrity check failed: " + item["path"])
        verified = {
            str((manifest_path.parent / item["path"]).resolve()) for item in manifest["files"]
        }
        for key in ("detector_model", "recognizer_model", "piper_model"):
            if str(Path(config[key]).resolve()) not in verified:
                raise ValueError("Unverified " + key)
        if str(Path(config["piper_model"] + ".json").resolve()) not in verified:
            raise ValueError("Unverified voice configuration")
        speech_files = [p for p in Path(config["vosk_model"]).rglob("*") if p.is_file()]
        if not speech_files or any(str(p.resolve()) not in verified for p in speech_files):
            raise ValueError("Unverified speech model")
        signature = hashlib.sha256(Path(config["recognizer_model"]).read_bytes()).hexdigest()
        if config["model_version"] != "sface:" + signature:
            raise ValueError("model_version must identify exact SFace bytes")
    return config
