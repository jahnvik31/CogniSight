"""Speaking to the wearer, and listening for a few short commands.

Speech and listening use moonshine-voice: one offline library for both
(Moonshine streaming speech-to-text, Kokoro/Piper voices for speech). Sound
goes to the Pi's default output, so paired Bluetooth earphones work once they
are the default device. If the library or audio device is missing, the rest of
CogniSight keeps running and the dashboard says why.
"""

import math
import re
import shutil
import subprocess
import threading
import time

COOLDOWN_SECONDS = 120


def introduction(name, relationship=""):
    relationship = " ".join((relationship or "").split())
    if not relationship:
        return "This is {}.".format(name)
    lowered = relationship.lower()
    if lowered.startswith(("your ", "my ", "the ", "a ", "an ")):
        if lowered.startswith("my "):
            relationship = "your " + relationship[3:]
        return "This is {}, {}.".format(name, relationship)
    return "This is {}, your {}.".format(name, relationship)


_COMMANDS = [
    ("stop", re.compile(r"\b(stop|quiet|shush|enough|silence|cancel)\b")),
    ("go", re.compile(r"\b(take me to|where('s| is| are)|how do i get to|go to|want to go|need to go|need the|find the|show me the|way to)\b")),
    ("more", re.compile(r"\b(tell me more|more about|who is (he|she|they) again)\b")),
    ("who", re.compile(r"\b(who('s| is) (this|that|it|here)|who am i (talking|speaking) to|say (that|it) again|repeat)\b")),
]


def parse_command(text):
    """'stop', 'go', 'who', 'more', or None for anything else. 'go' means the
    wearer asked for a room; the caller works out which one."""
    lowered = " ".join((text or "").lower().replace("’", "'").split())
    for command, pattern in _COMMANDS:
        if pattern.search(lowered):
            return command
    return None


class Announcer:
    """Decides when to speak. A person is introduced the moment they are
    recognised. They are introduced again only after they have been out of
    view for ``cooldown`` seconds, so someone who stays in the room is not
    re-introduced over and over."""

    def __init__(self, speaker, cooldown=COOLDOWN_SECONDS, clock=time.monotonic, on_said=None):
        self.speaker = speaker
        self.cooldown = cooldown
        self.enabled = True
        self.error = None
        self._clock = clock
        self._on_said = on_said
        self._last = {}
        self._lock = threading.Lock()

    def seen(self, name, relationship=""):
        """Call for each recognised person on each pass. Returns what was said, or None."""
        with self._lock:
            now = self._clock()
            if not self.can_speak():
                # Not heard, so not counted: they are introduced once speech works.
                return None
            previous = self._last.get(name, -math.inf)
            self._last[name] = now
            if now - previous < self.cooldown:
                return None
        return self.say(introduction(name, relationship))

    def can_speak(self):
        return self.enabled and bool(getattr(self.speaker, "available", True))

    def say(self, text):
        if not self.enabled:
            return None
        try:
            self.speaker.say(text)
            self.error = None
        except Exception as exc:  # Bluetooth dropped, no output device
            self.error = "Could not play speech: {}".format(exc)
            return None
        if not getattr(self.speaker, "available", True):
            return None  # nothing was heard, so nothing is reported as said
        if self._on_said:
            self._on_said(text)
        return text

    def stop(self):
        try:
            self.speaker.stop()
        except Exception:
            pass

    def handle(self, text, in_view):
        """Act on a heard phrase. ``in_view`` is a list of people (with
        ``name``, ``relationship``, ``note``) currently recognised."""
        command = parse_command(text)
        if command == "stop":
            self.stop()
        elif command == "who":
            if in_view:
                self.say(" ".join(introduction(p.name, p.relationship) for p in in_view))
            else:
                self.say("I don't see anyone I know right now.")
        elif command == "more":
            notes = [p.note for p in in_view if p.note]
            if notes:
                self.say(" ".join(notes))
            elif in_view:
                self.say(introduction(in_view[0].name, in_view[0].relationship))
            else:
                self.say("I don't see anyone I know right now.")
        return command


# ---------------------------------------------------------------- speakers


class NullSpeaker:
    available = False

    def __init__(self, error="Speech is not set up."):
        self.error = error

    def say(self, text):
        pass

    def stop(self):
        pass

    def is_talking(self):
        return False


class EspeakSpeaker:
    """Fallback when moonshine-voice cannot load: the espeak-ng command."""

    available = True
    error = None

    def __init__(self):
        self.binary = shutil.which("espeak-ng") or shutil.which("espeak")
        if not self.binary:
            raise RuntimeError("espeak-ng is not installed")
        self._process = None

    def say(self, text):
        self.stop()
        self._process = subprocess.Popen(
            [self.binary, "-s", "150", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    def stop(self):
        if self._process and self._process.poll() is None:
            self._process.terminate()

    def is_talking(self):
        return bool(self._process and self._process.poll() is None)


class MoonshineSpeaker:
    available = True
    error = None

    def __init__(self, voice=None):
        from moonshine_voice import TextToSpeech

        tts = TextToSpeech().language("en_us")
        if voice:
            tts = tts.voice(voice)
        self._tts = tts.load()

    def say(self, text):
        # Queued, so a direction never cuts off an introduction.
        self._tts.say(text)

    def stop(self):
        self._tts.stop()

    def is_talking(self):
        return bool(self._tts.is_talking())


def load_speaker(voice=None):
    """The best speaker available here. Never raises."""
    errors = []
    try:
        return MoonshineSpeaker(voice)
    except Exception as exc:  # missing library, no audio device, download failure
        errors.append("Moonshine: {}".format(exc))
    try:
        speaker = EspeakSpeaker()
        speaker.error = "Using espeak-ng because " + errors[0]
        return speaker
    except Exception as exc:
        errors.append("espeak-ng: {}".format(exc))
    return NullSpeaker("; ".join(errors))


class Listener:
    """Moonshine speech-to-text on the default microphone."""

    def __init__(self, on_line, model="tiny"):
        from moonshine_voice import MicTranscriber, ModelArch

        arch = {
            "tiny": ModelArch.TINY_STREAMING,
            "small": ModelArch.SMALL_STREAMING,
            "medium": ModelArch.MEDIUM_STREAMING,
        }.get(model, ModelArch.TINY_STREAMING)
        self._mic = MicTranscriber().language("en").model_arch(arch)
        self._mic.on_line(lambda line: on_line(line.text))
        self._mic.load()
        self._running = False

    def start(self):
        if not self._running:
            self._mic.start()
            self._running = True

    def stop(self):
        if self._running:
            self._mic.stop()
            self._running = False

    def close(self):
        self.stop()
        self._mic.close()


def download_voice_models(listen_model="tiny"):
    """Fetch speech models ahead of time so the demo runs offline."""
    from moonshine_voice import MicTranscriber, ModelArch, TextToSpeech

    TextToSpeech().language("en_us").load().close()
    arch = {"tiny": ModelArch.TINY_STREAMING, "small": ModelArch.SMALL_STREAMING}.get(
        listen_model, ModelArch.TINY_STREAMING
    )
    MicTranscriber().language("en").model_arch(arch).load().close()
