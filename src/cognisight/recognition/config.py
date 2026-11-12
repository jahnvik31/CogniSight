"""Explicit device/model configuration; no runtime downloads."""

import hashlib
import json
import math
import ipaddress
import re
from pathlib import Path


def _port(value, minimum=1):
    if type(value) is not int or not minimum <= value <= 65535:
        raise ValueError("Invalid configured service port")
    return value


def _exact_host(value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("Caregiver hosts must be exact DNS names or IP addresses")
    host = value.lower()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if len(host) > 253 or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in host.split(".")
        ):
            raise ValueError(
                "Caregiver hosts must not contain wildcards, schemes, ports, or paths"
            )
    else:
        if address.is_unspecified or address.is_multicast:
            raise ValueError("Caregiver hosts must identify a specific unicast address")
    return host


def _optional_services(config):
    options = {}
    for name in ("navigation", "caregiver"):
        value = config.get(name, {})
        if not isinstance(value, dict) or type(value.get("enabled", False)) is not bool:
            raise ValueError(name + " must be an object with a boolean enabled flag")
        options[name] = dict(value)
        options[name].setdefault("enabled", False)
    navigation, caregiver = options["navigation"], options["caregiver"]
    navigation.setdefault("gpsd_host", "127.0.0.1")
    navigation.setdefault("gpsd_port", 2947)
    navigation.setdefault("fix_max_age", 10)
    if navigation["gpsd_host"] not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("GPSD must connect through loopback")
    _port(navigation["gpsd_port"])
    age = navigation["fix_max_age"]
    if (
        isinstance(age, bool)
        or not isinstance(age, (float, int))
        or not math.isfinite(age)
        or not 0 < age <= 300
    ):
        raise ValueError(
            "Navigation fix_max_age must be finite and between zero and 300 seconds"
        )
    caregiver.setdefault("backend_port", 8766)
    caregiver.setdefault("allowed_hosts", [])
    _port(caregiver["backend_port"], minimum=1024)
    if not isinstance(caregiver["allowed_hosts"], list):
        raise ValueError("Caregiver allowed_hosts must be a list")
    caregiver["allowed_hosts"] = [
        _exact_host(value) for value in caregiver["allowed_hosts"]
    ]
    if caregiver["enabled"] and not caregiver["allowed_hosts"]:
        raise ValueError("Enabling caregiver access requires explicit allowed_hosts")
    return options


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
    config.update(_optional_services(config))
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
            str((manifest_path.parent / item["path"]).resolve())
            for item in manifest["files"]
        }
        for key in ("detector_model", "recognizer_model", "piper_model"):
            if str(Path(config[key]).resolve()) not in verified:
                raise ValueError("Unverified " + key)
        if str(Path(config["piper_model"] + ".json").resolve()) not in verified:
            raise ValueError("Unverified voice configuration")
        speech_files = [p for p in Path(config["vosk_model"]).rglob("*") if p.is_file()]
        if not speech_files or any(
            str(p.resolve()) not in verified for p in speech_files
        ):
            raise ValueError("Unverified speech model")
        signature = hashlib.sha256(
            Path(config["recognizer_model"]).read_bytes()
        ).hexdigest()
        if config["model_version"] != "sface:" + signature:
            raise ValueError("model_version must identify exact SFace bytes")
    return config
