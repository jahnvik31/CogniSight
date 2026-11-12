"""Offline headset audio with bounded work and explicit device routing.

Hardware imports happen only in the connection worker. Missing dependencies or
models leave audio unavailable; no default-device or network fallback exists.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import queue
import re
import threading
import time
from typing import Callable


COMMAND_PHRASES = (
    "cogni who is this",
    "cogni tell me more",
    "cogni when did i last see them",
    "cogni repeat",
    "cogni stop",
    "cogni pause recognition",
    "cogni resume recognition",
    "[unk]",
)


def select_usb_device(devices, requested: str, direction: str) -> int:
    """Resolve a route without allowing implicit defaults or ambiguous devices."""
    if (
        direction not in ("input", "output")
        or not isinstance(requested, str)
        or not requested.strip()
    ):
        raise ValueError("An explicit USB audio device is required")
    requested = requested.strip().casefold()
    candidates = [
        (i, d)
        for i, d in enumerate(devices)
        if "usb" in d["name"].casefold() and d.get("max_" + direction + "_channels", 0) > 0
    ]
    exact = [i for i, d in candidates if d["name"].casefold() == requested]
    matches = exact or [i for i, d in candidates if requested in d["name"].casefold()]
    if len(matches) != 1:
        raise ValueError("Audio selection must uniquely identify a USB " + direction + " device")
    return matches[0]


class VocabularyError(ValueError):
    """The selected ASR model cannot represent every configured command word."""


def validate_grammar(model, phrases):
    words = {word for phrase in phrases if phrase != "[unk]" for word in phrase.split()}
    if any(model.vosk_model_find_word(word) < 0 for word in words):
        raise VocabularyError("Speech model does not contain all command words")


@dataclass
class SpeechItem:
    text: str
    valid: Callable[[], bool]
    priority: int
    generation: int
    sequence: int


class SpeechQueue:
    """Stable priority queue; explicit requests may evict automatic messages."""

    def __init__(self, capacity=8):
        self.capacity = capacity
        self._items = []
        self._sequence = 0
        self._ready = threading.Condition()

    def put(self, text, valid, priority, generation):
        with self._ready:
            if any(item.text == text for item in self._items):
                return False
            if len(self._items) >= self.capacity:
                lowest = min(self._items, key=lambda i: (i.priority, -i.sequence))
                if priority <= lowest.priority:
                    return False
                self._items.remove(lowest)
            self._sequence += 1
            self._items.append(SpeechItem(text, valid, priority, generation, self._sequence))
            self._ready.notify()
            return True

    def get(self, timeout=0.2):
        with self._ready:
            if not self._items:
                self._ready.wait(timeout)
            if not self._items:
                return None
            item = min(self._items, key=lambda i: (-i.priority, i.sequence))
            self._items.remove(item)
            return item

    def clear(self):
        with self._ready:
            self._items.clear()
            self._ready.notify_all()


class AudioEngine:
    """USB microphone -> Vosk commands; Piper -> USB headset.

    ``on_health(component, state)`` receives short status codes, never exception
    strings (which may contain user paths or transcription text).
    """

    def __init__(self, config, on_command, on_health):
        self.config = dict(config)
        self.prefix = self.config.get("command_prefix", "computer").strip().casefold()
        self.on_command = on_command
        self.on_health = on_health
        self._speech = SpeechQueue(8)
        self._samples = queue.Queue(maxsize=16)
        self._stop = threading.Event()
        self._available = threading.Event()
        self._speaking = threading.Event()
        self._reset_asr = threading.Event()
        self._lock = threading.RLock()
        self._route_lock = threading.RLock()
        self._generation = 0
        self._threads = []
        self._stream = None
        self._output = None
        self._sd = None
        self._np = None
        self._recognizer = None
        self._voice = None
        self._input_index = self._output_index = None
        self._input_name = self._output_name = None
        self._input_rate = self._output_rate = None

    @property
    def available(self):
        return self._available.is_set()

    @property
    def speaking(self):
        return self._speaking.is_set()

    def _health(self, state):
        for component in ("microphone", "playback"):
            self.on_health(component, state)

    def start(self):
        if self._threads:
            return
        self._stop.clear()
        self._threads = [
            threading.Thread(target=target, daemon=True, name=name)
            for target, name in ((self._listen, "headset-input"), (self._speak, "headset-output"))
        ]
        for thread in self._threads:
            thread.start()

    def close(self):
        self._stop.set()
        self._available.clear()
        self.cancel()
        with self._route_lock:
            if self._stream is not None:
                try:
                    self._stream.abort()
                except Exception:
                    pass
        for thread in self._threads:
            if thread is not threading.current_thread():
                thread.join(timeout=3)
        self._threads.clear()

    def say(self, text: str, valid=lambda: True, priority: int = 0):
        if not self.available or not text or len(text) > 1500:
            return False
        # Never teach a spoken stop phrase that the active recognizer could hear.
        normalized = " ".join(re.sub(r"[^a-z ]", " ", text.casefold()).split())
        if (
            "cogni stop" in normalized
            or self.prefix + " stop" in normalized
            or not self._safe_valid(valid)
        ):
            return False
        with self._lock:
            return self._speech.put(text, valid, priority, self._generation)

    def cancel(self):
        with self._lock:
            self._generation += 1
            self._speech.clear()
            # Output teardown takes this same lock. Abort only our stream, and
            # never race a native close after retrieving a stale stream handle.
            if self._output is not None:
                try:
                    self._output.abort()
                except Exception:
                    pass
        self._reset_asr.set()

    @staticmethod
    def _safe_valid(valid):
        try:
            return bool(valid())
        except Exception:
            return False

    def _dispatch(self, text):
        from .commands import parse_command

        if text.casefold().startswith(self.prefix + " "):
            text = "cogni " + text[len(self.prefix) + 1 :]
        intent = parse_command(text)
        if intent is None or (self.speaking and intent != "stop"):
            return
        if intent == "stop":
            self.cancel()
        self.on_command(intent)

    def _callback(self, data, frames, timing, status):
        if status:
            self._reset_asr.set()
        try:
            self._samples.put_nowait(bytes(data))
        except queue.Full:
            self._reset_asr.set()
            self._drain_samples()

    def _drain_samples(self):
        while True:
            try:
                self._samples.get_nowait()
            except queue.Empty:
                break

    def _connect(self):
        import numpy as np
        import sounddevice as sd
        from vosk import Model, KaldiRecognizer, SetLogLevel
        from piper import PiperVoice

        model = Path(self.config.get("vosk_model", ""))
        voice = Path(self.config.get("piper_model", ""))
        if not model.is_dir() or not (model / "am" / "final.mdl").is_file():
            raise ValueError("Local speech recognition model is missing")
        if not voice.is_file() or not Path(str(voice) + ".json").is_file():
            raise ValueError("Local synthesis model is missing")
        if not re.fullmatch(r"[a-z]+", self.prefix):
            raise ValueError("Command prefix must be one English word")
        devices = sd.query_devices()
        input_id = select_usb_device(
            devices, self._input_name or self.config.get("input_device", ""), "input"
        )
        output_id = select_usb_device(
            devices, self._output_name or self.config.get("output_device", ""), "output"
        )
        input_rate = int(self.config.get("input_rate") or devices[input_id]["default_samplerate"])
        output_rate = int(devices[output_id]["default_samplerate"])
        if input_rate < 8000 or input_rate > 192000 or output_rate < 8000 or output_rate > 192000:
            raise ValueError("Invalid headset sample rate")
        sd.check_input_settings(device=input_id, channels=1, dtype="int16", samplerate=input_rate)
        sd.check_output_settings(
            device=output_id, channels=1, dtype="int16", samplerate=output_rate
        )
        SetLogLevel(-1)
        self._sd, self._np = sd, np
        if self._voice is None:
            self._voice = PiperVoice.load(str(voice), use_cuda=False)
        if not hasattr(self, "_vosk_model"):
            self._vosk_model = Model(str(model))
        phrases = tuple(
            phrase.replace("cogni ", self.prefix + " ", 1) for phrase in COMMAND_PHRASES
        )
        validate_grammar(self._vosk_model, phrases)
        self._recognizer = KaldiRecognizer(self._vosk_model, input_rate, json.dumps(phrases))
        self._input_index, self._output_index = input_id, output_id
        self._input_name, self._output_name = devices[input_id]["name"], devices[output_id]["name"]
        self._input_rate, self._output_rate = input_rate, output_rate
        self._drain_samples()
        with self._route_lock:
            if self._stop.is_set():
                return
            self._stream = sd.RawInputStream(
                device=input_id,
                samplerate=input_rate,
                channels=1,
                dtype="int16",
                blocksize=max(1, input_rate // 10),
                callback=self._callback,
            )
            self._stream.start()
            self._available.set()
        self._health("ready")

    def _check_routes(self):
        devices = self._sd.query_devices()
        # Replugging may reorder indices; require reconnect rather than letting an
        # old index address a different device. Names remain the selection key.
        if (
            select_usb_device(devices, self._input_name, "input") != self._input_index
            or select_usb_device(devices, self._output_name, "output") != self._output_index
        ):
            raise RuntimeError("Headset route changed")
        with self._route_lock:
            if self._stream is None or not self._stream.active:
                raise RuntimeError("Input stream stopped")

    def _disconnect(self, state="unavailable"):
        self._available.clear()
        self.cancel()
        # Only the listener owns input close/replacement. The route lock also
        # serializes shutdown's abort with native close, and detaching before
        # close makes repeated disconnects idempotent.
        with self._route_lock:
            stream, self._stream = self._stream, None
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass
        self._drain_samples()
        self._health(state)

    def _listen(self):
        while not self._stop.is_set():
            try:
                if not self.available:
                    # Output failures invalidate availability from a different
                    # worker. Retire its still-open input route before opening
                    # another; otherwise every reconnect leaks a microphone.
                    self._disconnect()
                    self._connect()
                check_at = time.monotonic() + 1
                while not self._stop.is_set() and self.available:
                    if self._reset_asr.is_set():
                        self._reset_asr.clear()
                        self._recognizer.Reset()
                        self._drain_samples()
                    try:
                        data = self._samples.get(timeout=0.1)
                    except queue.Empty:
                        data = None
                    if data is not None and self._recognizer.AcceptWaveform(data):
                        result = json.loads(self._recognizer.Result())
                        self._dispatch(result.get("text", ""))
                    if time.monotonic() >= check_at:
                        self._check_routes()
                        check_at = time.monotonic() + 1
            except VocabularyError:
                self._disconnect("vocabulary_missing")
                self._stop.wait(5)
            except ImportError:
                self._disconnect("dependency_missing")
                self._stop.wait(5)
            except Exception:
                self._disconnect()
                self._stop.wait(5)
        self._disconnect()

    def _item_valid(self, item):
        return (
            not self._stop.is_set()
            and self.available
            and item.generation == self._generation
            and self._safe_valid(item.valid)
        )

    def _speak(self):
        while not self._stop.is_set():
            item = self._speech.get(0.2)
            if item is None or not self._item_valid(item):
                continue
            self._speaking.set()
            try:
                # Check the selected identity before synthesis AND every playback
                # block; a person leaving view invalidates queued/current speech.
                for chunk in self._voice.synthesize(item.text):
                    if not self._item_valid(item):
                        break
                    samples = self._np.frombuffer(chunk.audio_int16_bytes, dtype=self._np.int16)
                    if chunk.sample_rate != self._output_rate:
                        count = max(1, int(len(samples) * self._output_rate / chunk.sample_rate))
                        samples = self._np.interp(
                            self._np.arange(count) * chunk.sample_rate / self._output_rate,
                            self._np.arange(len(samples)),
                            samples,
                        ).astype(self._np.int16)
                    self._check_routes()
                    stream = self._sd.RawOutputStream(
                        device=self._output_index,
                        channels=1,
                        dtype="int16",
                        samplerate=self._output_rate,
                    )
                    try:
                        if not self._item_valid(item):
                            continue
                        with self._lock:
                            # Do not invoke external visibility callbacks while
                            # holding the audio lock: runtime -> audio is the
                            # normal lock order used when queuing speech.
                            if item.generation != self._generation or not self.available:
                                continue
                            self._output = stream
                            stream.start()
                        size = max(1, self._output_rate // 20)
                        for offset in range(0, len(samples), size):
                            if not self._item_valid(item):
                                with self._lock:
                                    stream.abort()
                                break
                            stream.write(samples[offset : offset + size].tobytes())
                    finally:
                        with self._lock:
                            self._output = None
                            try:
                                stream.stop()
                            finally:
                                stream.close()
            except Exception:
                self._available.clear()
                self.cancel()
                self._health("unavailable")
            finally:
                with self._lock:
                    self._output = None
                self._speaking.clear()
                self._reset_asr.set()
