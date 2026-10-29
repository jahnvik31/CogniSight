import queue
import threading
import time
from typing import List, Optional
from app.config.settings import settings
from app.utils.logging_config import logger

try:
    import pyttsx3
    import pythoncom  # Windows COM initialization for multi-threaded SAPI5 audio

    TTS_AVAILABLE = True
except Exception as e:
    TTS_AVAILABLE = False
    logger.warning(f"pyttsx3 / pythoncom initialization notice: {e}")


class VoiceAssistant:
    """Non-blocking Voice Assistant Text-To-Speech engine for CogniSight.

    Provides spoken announcements, immediate enrollment feedback, and periodic
    30-second memory reminders.
    """

    def __init__(
        self,
        cooldown_seconds: float = settings.SPEECH_COOLDOWN_SECONDS,
        reminder_interval_seconds: float = settings.REMINDER_INTERVAL_SECONDS,
        enabled: bool = settings.VOICE_ENABLED,
    ):
        self.cooldown_seconds = cooldown_seconds
        self.reminder_interval_seconds = reminder_interval_seconds
        self.enabled = enabled and TTS_AVAILABLE

        self.last_spoken_text: str = ""
        self.last_spoken_time: float = 0.0

        self.speech_queue: queue.Queue = queue.Queue()
        self.stop_event: threading.Event = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None

        if self.enabled:
            self._start_worker()

    def _start_worker(self):
        """Starts background thread to process speech queue without blocking video frames."""
        self.worker_thread = threading.Thread(target=self._speech_worker, daemon=True)
        self.worker_thread.start()

    def _speech_worker(self):
        """Worker loop executing pyttsx3 speech synthesis with Windows COM initialization."""
        while not self.stop_event.is_set():
            try:
                text = self.speech_queue.get(timeout=0.5)
                if text and self.enabled:
                    logger.info(f"[VOICE ASSISTANT SPEAKING]: '{text}'")
                    try:
                        pythoncom.CoInitialize()
                        try:
                            engine = pyttsx3.init()
                            engine.setProperty("rate", 160)  # Speech rate
                            engine.setProperty("volume", 1.0)  # Volume
                            engine.say(text)
                            engine.runAndWait()
                            del engine
                        finally:
                            pythoncom.CoUninitialize()
                    except Exception as err:
                        logger.error(f"Error during TTS playback: {err}")
                self.speech_queue.task_done()
            except queue.Empty:
                continue

    def speak(self, text: str, force: bool = False) -> bool:
        """Enqueues text for spoken audio output with periodic 30-second reminder logic.

        Args:
            text: Sentence to speak.
            force: If True, bypasses cooldown and periodic reminder checks.

        Returns:
            bool: True if queued for speech, False if throttled.
        """
        if not text or not text.strip():
            return False

        now = time.time()
        elapsed = now - self.last_spoken_time

        if not force:
            if text == self.last_spoken_text:
                if elapsed < self.reminder_interval_seconds:
                    return False
            else:
                if elapsed < self.cooldown_seconds:
                    return False

        self.last_spoken_text = text
        self.last_spoken_time = now

        if self.enabled:
            self.speech_queue.put(text)
            logger.info(f"Queued voice announcement: '{text}' (Elapsed: {elapsed:.1f}s)")
        else:
            logger.info(f"[VOICE ASSISTANT FALLBACK]: '{text}'")

        return True

    def announce_enrollment(self, name: str, relationship: str = "") -> bool:
        """Immediate voice announcement when a new person is enrolled or face embedding saved."""
        rel_str = f", your {relationship}," if relationship else ""
        announcement = f"Successfully enrolled {name}{rel_str} into CogniSight memory!"
        return self.speak(announcement, force=True)

    def speak_sequence(self, utterances: List[str], force: bool = True) -> int:
        """Enqueues an ordered sequence of spoken announcements (e.g. route directions).

        Using force=True (default) ensures consecutive route steps are not discarded
        by the rate-limiting cooldown timer.

        Args:
            utterances: List of sentences to be spoken sequentially.
            force: Whether to bypass rate-limiting cooldown. Defaults to True.

        Returns:
            int: Number of utterances successfully queued.
        """
        count = 0
        for text in utterances:
            if self.speak(text, force=force):
                count += 1
        return count

    def clear_queue(self):
        """Clears any pending queued utterances from speech synthesis buffer."""
        while not self.speech_queue.empty():
            try:
                self.speech_queue.get_nowait()
                self.speech_queue.task_done()
            except (queue.Empty, ValueError):
                break

    def stop(self):
        """Stops background worker thread."""
        self.clear_queue()
        self.stop_event.set()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)
