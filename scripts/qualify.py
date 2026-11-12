#!/usr/bin/env python3
"""Collect actual device evidence and evaluate anonymous, held-out trial CSVs.

No frames, biometric vectors, audio, names, transcripts, device serials, or
network addresses are included. A smoke check is not a release qualification.
CSV columns: kind,encounter_id,correct,latency_ms,intent,speaker_id.
Kinds: recognition,command,unknown,stop. correct: 0/1. Intent/speaker_id are
required for command coverage (opaque IDs only); each independent encounter
gets a distinct opaque encounter_id. Repeated rows are deduplicated.
"""
import argparse
import csv
import json
import importlib.metadata
import math
import os
import platform
import resource
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

INTENTS = ("identify", "context", "history", "repeat", "stop", "pause", "resume")


def percentile(values, fraction=0.95):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def evaluate_trials(rows):
    grouped = {kind: [] for kind in ("recognition", "command", "unknown", "stop")}
    seen = {}
    for row in rows:
        kind = row.get("kind")
        encounter = (row.get("encounter_id") or "").strip()
        if kind not in grouped or not encounter or row.get("correct") not in ("0", "1"):
            raise ValueError(
                "Each trial requires a valid kind, opaque encounter_id, and correct=0/1"
            )
        raw_latency = (row.get("latency_ms") or "").strip()
        latency = float(raw_latency) if raw_latency else None
        if latency is not None and (not math.isfinite(latency) or latency < 0):
            raise ValueError("latency_ms must be finite and nonnegative")
        if kind != "unknown" and latency is None:
            raise ValueError("Timing is required for recognition, command, and stop trials")
        intent, speaker = (row.get("intent") or "").strip(), (row.get("speaker_id") or "").strip()
        if kind == "command" and (intent not in INTENTS or not speaker):
            raise ValueError("Command trials require a supported intent and opaque speaker_id")
        value = (row["correct"] == "1", latency, intent, speaker)
        key = (kind, encounter)
        if key in seen:
            if seen[key] != value:
                raise ValueError("Conflicting duplicate encounter rows")
            continue
        seen[key] = value
        grouped[kind].append(value)
    report = {
        "release_qualified": False,
        "evidence_note": "Anonymous supplied trials; independence and ground truth require reviewer verification. Hardware/soak gates are separate.",
    }
    for kind, trials in grouped.items():
        count = len(trials)
        correct = sum(t[0] for t in trials)
        latencies = [t[1] for t in trials if t[1] is not None]
        result = {
            "count": count,
            "correct": correct,
            "accuracy": correct / count if count else None,
            "p95_latency_ms": percentile(latencies),
        }
        if kind == "unknown":
            result["false_named_announcements"] = count - correct
            result["false_accept_upper_95"] = (
                1 - 0.05 ** (1 / count) if count and correct == count else None
            )
            result["acceptance_passed"] = count >= 300 and correct == count
        elif kind == "command":
            speakers = {t[3] for t in trials}
            coverage = Counter((t[3], t[2]) for t in trials)
            covered = bool(speakers) and all(
                coverage[(s, i)] >= 20 for s in speakers for i in INTENTS
            )
            result["speakers_count"] = len(speakers)
            result["per_speaker_intent_coverage_passed"] = covered
            result["acceptance_passed"] = bool(
                count and covered and correct / count >= 0.95 and percentile(latencies) <= 2000
            )
        else:
            limit = 3000 if kind == "recognition" else 1000
            result["acceptance_passed"] = bool(
                count and correct / count >= 0.95 and percentile(latencies) <= limit
            )
        report[kind] = result
    return report


def _read(path):
    try:
        return Path(path).read_text().strip().strip("\x00")
    except (OSError, UnicodeError):
        return None


def _command(args):
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=3, check=True
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def hardware_report():
    """Read non-identifying evidence; never copy /proc/cpuinfo serial fields."""
    system = platform.system()
    model = _read("/proc/device-tree/model") if system == "Linux" else None
    os_release = {}
    for line in (_read("/etc/os-release") or "").splitlines():
        key, _, value = line.partition("=")
        if key in ("ID", "VERSION_ID", "PRETTY_NAME"):
            os_release[key] = value.strip('"')
    thermal = _read("/sys/class/thermal/thermal_zone0/temp")
    try:
        temperature = float(thermal) / 1000 if thermal else None
    except ValueError:
        temperature = None
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_bytes = rss if system == "Darwin" else rss * 1024
    throttled = _command(["vcgencmd", "get_throttled"]) if system == "Linux" else None
    clock_sync = (
        _command(["timedatectl", "show", "-p", "NTPSynchronized", "--value"])
        if system == "Linux"
        else None
    )
    versions = {}
    for package in (
        "numpy",
        "opencv-python-headless",
        "picamera2",
        "vosk",
        "piper-tts",
        "sounddevice",
        "Flask",
        "Flask-WTF",
        "waitress",
    ):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    memory = {}
    for line in (_read("/proc/meminfo") or "").splitlines():
        if line.startswith(("MemTotal:", "MemAvailable:")):
            key, value = line.split(":", 1)
            memory[key] = value.strip()
    return {
        "schema_version": 1,
        "release_qualified": False,
        "platform": {
            "system": system,
            "machine": platform.machine(),
            "python": platform.python_version(),
            "os_release": os_release,
            "pi_model": model,
            "is_target_pi5_64bit": bool(
                model and "Raspberry Pi 5" in model and platform.machine() == "aarch64"
            ),
        },
        "installed_packages": versions,
        "memory": memory,
        "measurement": {
            "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "clock_synchronized": clock_sync == "yes" if clock_sync else None,
            "temperature_c": temperature,
            "throttled_flags": throttled,
            "qualification_process_peak_rss_bytes": rss_bytes,
            "rss_note": "This process only; not combined module memory or a soak measurement.",
        },
        "acceptance": {
            name: "pending"
            for name in (
                "camera_capture",
                "recognition_inference",
                "usb_capture_playback",
                "offline_operation",
                "held_out_accuracy",
                "unknown_300_encounters",
                "voice_accuracy",
                "stop_latency",
                "gallery_100_profiles",
                "two_hour_soak",
                "combined_memory_under_4gb",
                "no_throttling",
                "device_reconnect",
            )
        },
    }


def smoke(config_path, seconds, interactive=False):
    """Actual camera/inference timings; headset check requires explicit interaction."""
    from cognisight.recognition.config import load_config
    from cognisight.recognition.vision import Vision

    config = load_config(config_path)
    vision = Vision(config)
    result = {
        "camera_inference": {"state": "not_run"},
        "audio": {"state": "pending_interactive_check"},
    }
    try:
        vision.start()
        deadline = time.monotonic() + seconds
        times, frames, face_observations = [], 0, 0
        while time.monotonic() < deadline:
            packet = vision.read()
            started = time.monotonic()
            detected = vision.detect(packet.image)
            times.append((time.monotonic() - started) * 1000)
            frames += 1
            face_observations += len(detected)
        result["camera_inference"] = {
            "state": "smoke_passed",
            "frames": frames,
            "face_observations": face_observations,
            "p95_inference_ms": percentile(times),
            "note": "Inference time only, not appearance-to-speech latency or identity accuracy.",
        }
    finally:
        vision.close()
    if interactive:
        if not sys.stdin.isatty():
            raise ValueError("--interactive requires a terminal and a human headset check")
        from cognisight.recognition.audio import AudioEngine

        health, commands = {}, []
        audio = AudioEngine(
            config,
            lambda intent: commands.append(intent),
            lambda component, state: health.update({component: state}),
        )
        try:
            audio.start()
            deadline = time.monotonic() + 30
            while not audio.available and time.monotonic() < deadline:
                time.sleep(0.1)
            if not audio.available:
                result["audio"] = {"state": "failed", "health": health}
            else:
                audio.say("This is the headset qualification check.")
                heard = (
                    input("Did you hear the check through the selected USB headset? [y/N] ")
                    .strip()
                    .lower()
                    == "y"
                )
                print("Speak one supported prefixed command into the headset within ten seconds.")
                deadline = time.monotonic() + 10
                while not commands and time.monotonic() < deadline:
                    time.sleep(0.1)
                result["audio"] = {
                    "state": "smoke_passed" if heard and commands else "failed",
                    "playback_human_confirmed": heard,
                    "command_detected": bool(commands),
                    "note": "One microphone/playback check; not voice accuracy or interruption qualification.",
                }
        finally:
            audio.close()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        help="Run actual camera/model smoke checks using verified local models",
    )
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Explicit headset playback/microphone human check",
    )
    parser.add_argument(
        "--trials", type=Path, help="Anonymous held-out trial CSV; never names/recordings"
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if not math.isfinite(args.seconds) or not 1 <= args.seconds <= 7200:
        parser.error("--seconds must be between 1 and 7200")
    if args.interactive and not args.config:
        parser.error("--interactive requires --config")
    report = hardware_report()
    code = 0
    if args.config:
        try:
            report["smoke"] = smoke(args.config, args.seconds, args.interactive)
            if report["smoke"]["camera_inference"]["state"] == "smoke_passed":
                report["acceptance"]["camera_capture"] = "smoke_passed"
                report["acceptance"]["recognition_inference"] = "smoke_passed"
            if report["smoke"]["audio"]["state"] == "smoke_passed":
                report["acceptance"]["usb_capture_playback"] = "smoke_passed"
        except Exception as exc:
            # Exceptions can carry local paths or data; report type only.
            report["smoke"] = {
                "state": "failed",
                "error_type": type(exc).__name__,
                "action": "Check installed dependencies, verified assets, and physical devices.",
            }
            code = 1
    if args.trials:
        try:
            with args.trials.open(newline="") as stream:
                report["trials"] = evaluate_trials(csv.DictReader(stream))
        except (OSError, ValueError, csv.Error):
            report["trials"] = {
                "state": "invalid",
                "action": "Validate anonymous trial CSV schema and finite timings.",
            }
            code = 1
    # No script can turn a short smoke check into full hardware certification.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print("Qualification evidence written; release acceptance remains pending unmeasured gates.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
