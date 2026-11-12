"""Single camera owner, expiring context, and isolated module events."""

import logging
import queue
import sqlite3
import threading
import time
from datetime import datetime, timezone
from .matching import Gallery, normalize
from .tracking import Tracker
from .types import RecognitionEvent, clock_utc

LOG = logging.getLogger(__name__)


class Runtime:
    def __init__(self, store, config, vision=None, audio=None):
        self.store, self.config, self.vision, self.audio = store, config, vision, audio
        self.lock = threading.RLock()
        self.tracker = Tracker()
        self.paused = False
        self.enrollment = False
        self.samples = []
        self.enrollment_target = None
        self.enrollment_deadline = 0
        self.sample_frame = None
        self.sample_time = float("-inf")
        self.now = time.monotonic()
        self.utc = None
        self.context_person = None
        self.previous = {}
        self.encounter_last = {}
        self.last_response = None
        self.health = {
            "camera": "not_started",
            "microphone": "not_started",
            "playback": "not_started",
            "model": "uncalibrated" if not config.get("calibrated") else "ready",
            "storage": "ready",
            "clock": "unverified",
        }
        self.events = []
        self.stopping = threading.Event()
        self.gallery_revision = -1
        self.gallery = Gallery(
            store.gallery(config["model_version"]), config["threshold"], config["margin"]
        )

    def on_health(self, component, state):
        with self.lock:
            self.health[component] = state

    def subscribe(self):
        channel = queue.Queue(maxsize=64)
        with self.lock:
            if len(self.events) >= 8:
                raise ValueError("Subscriber limit reached")
            self.events.append(channel)
        return channel

    def unsubscribe(self, channel):
        with self.lock:
            if channel in self.events:
                self.events.remove(channel)

    def _publish(self, event):
        data = RecognitionEvent(
            event.kind, event.track_id, event.person_id, self.utc, self.config["model_version"]
        ).to_dict()
        for channel in self.events:
            try:
                channel.put_nowait(data)
            except queue.Full:
                try:
                    channel.get_nowait()
                except queue.Empty:
                    pass
                try:
                    channel.put_nowait(data)
                except queue.Full:
                    pass

    def _expire_enrollment(self):
        if self.enrollment and time.monotonic() > self.enrollment_deadline:
            self.cancel_enrollment()

    def status(self):
        with self.lock:
            self._expire_enrollment()
            return dict(
                self.health,
                enrollment=self.enrollment,
                enrollment_samples=len(self.samples),
                paused=self.paused,
                calibrated=bool(self.config.get("calibrated")),
                schema_version=1,
            )

    def _valid_person(self, person_id, automatic=False):
        with self.lock:
            if self.paused or self.enrollment or not self.config.get("calibrated"):
                return False
            person = self.store.person(person_id)
            if not person or not person["active"]:
                return False
            if automatic:
                return any(t.person_id == person_id for t in self.tracker.visible(self.now))
            return self.tracker.recent(person_id, self.now)

    def _speak(self, text, person_id=None, priority=1):
        if not self.audio:
            return False
        if person_id:
            profile = self.store.person(person_id)
            version = profile["version"] if profile else None

            def valid():
                current = self.store.person(person_id)
                return bool(
                    current
                    and current["version"] == version
                    and self._valid_person(person_id, automatic=priority == 0)
                )

        else:
            valid = lambda: not self.stopping.is_set()
        if self.audio.say(text, valid=valid, priority=priority):
            self.last_response = (text, person_id)
            return True
        return False

    def observe(self, detections, now, utc):
        with self.lock:
            self.now, self.utc = now, utc
            self.health["clock"] = "available" if utc is not None else "unreliable"
            if self.paused or self.enrollment or not self.config.get("calibrated"):
                return
            events = self.tracker.update(detections, now)
            visible = self.tracker.visible(now)
            for track in visible:
                p = track.person_id
                if p not in self.encounter_last:
                    self.previous[p] = self.store.start_encounter(p, utc)
                self.encounter_last[p] = now
            for person_id, last in list(self.encounter_last.items()):
                if now - last >= 10:
                    self.store.end_encounter(person_id, utc)
                    del self.encounter_last[person_id]
            for event in events:
                self._publish(event)
            # Readiness can change after initial confirmation (startup/replug).
            if self.audio and self.audio.available:
                for track in visible:
                    person_id = track.person_id
                    if now - self.tracker.announced.get(person_id, float("-inf")) < 60:
                        continue
                    person = self.store.person(person_id)
                    if person and person["active"]:
                        name = person["pronunciation"] or person["name"]
                        text = (
                            "This is "
                            + name
                            + (", " + person["relationship"] if person["relationship"] else "")
                            + "."
                        )
                        if self._speak(text, person_id, priority=0):
                            self.tracker.should_announce(person_id, now)
            self.store.prune(utc)

    def _reset_presence(self):
        for person_id in self.encounter_last:
            try:
                self.store.end_encounter(person_id, self.utc)
            except sqlite3.Error:
                self.health["storage"] = "unavailable"
        self.encounter_last.clear()
        announced = self.tracker.announced
        self.tracker = Tracker()
        self.tracker.announced = announced
        self.context_person = None
        self.last_response = None
        if self.audio:
            self.audio.cancel()

    def command(self, intent, now=None):
        with self.lock:
            self.now = time.monotonic() if now is None else now
            if intent == "stop":
                if self.audio:
                    self.audio.cancel()
                return
            if intent == "pause":
                self.paused = True
                self._reset_presence()
                self._speak("Recognition paused.")
                return
            if intent == "resume":
                self.paused = False
                self._speak("Recognition resumed.")
                return
            if intent not in ("identify", "context", "history", "repeat"):
                return
            if not self.config.get("calibrated"):
                self._speak("Recognition requires caregiver calibration before use.")
                return
            if self.paused or self.enrollment:
                self._speak("Recognition is paused.")
                return
            if intent == "repeat":
                if self.last_response:
                    text, person_id = self.last_response
                    if not person_id or self._valid_person(person_id):
                        self._speak(text, person_id)
                    else:
                        self._speak("Please face the person again.")
                return
            if intent == "identify":
                target = self.tracker.primary(self.now, 640, 480)
                if target is None:
                    self.context_person = None
                    self._speak(
                        "Please face one person clearly. I cannot identify them confidently."
                    )
                    return
                self.context_person = target.person_id
            elif not self.context_person:
                target = self.tracker.primary(self.now, 640, 480)
                self.context_person = target.person_id if target else None
            person_id = self.context_person
            if not person_id or not self._valid_person(person_id):
                self.context_person = None
                self._speak("Please face the person again.")
                return
            person = self.store.person(person_id)
            name = person["pronunciation"] or person["name"]
            if intent == "identify":
                text = (
                    "This is "
                    + name
                    + (", " + person["relationship"] if person["relationship"] else "")
                    + "."
                )
            elif intent == "context":
                text = person["note"] or "No further verified information is saved."
            else:
                previous = self.previous.get(person_id)
                if self.utc is None or (previous is not None and previous > self.utc):
                    text = "The device clock is unreliable. I cannot report a previous recognition time."
                elif previous is None:
                    text = "There is no previous recorded recognition of " + name + "."
                else:
                    date = datetime.fromtimestamp(previous, timezone.utc).strftime(
                        "%d %B %Y at %H:%M UTC"
                    )
                    text = "The previous time I recognized " + name + " was " + date + "."
            self._speak(text, person_id)

    def begin_enrollment(self, person_id=None):
        with self.lock:
            if not self.vision:
                raise ValueError("Camera unavailable")
            if person_id and not self.store.person(person_id):
                raise ValueError("Profile not found")
            self._reset_presence()
            self.enrollment = True
            self.enrollment_target = person_id
            self.samples = []
            self.sample_frame = None
            self.sample_time = float("-inf")
            self.enrollment_deadline = time.monotonic() + 900

    def capture_sample(self):
        with self.lock:
            self._expire_enrollment()
            if not self.enrollment:
                raise ValueError("Start enrollment first")
            frame = self.vision.read()
            if frame.frame_id == self.sample_frame or frame.captured_at - self.sample_time < 0.2:
                return {
                    "accepted": False,
                    "count": len(self.samples),
                    "reason": "Wait for a new camera frame",
                }
            vector, reason = self.vision.enrollment_sample(frame.image)
            if vector is None:
                return {"accepted": False, "count": len(self.samples), "reason": reason}
            vector = normalize(vector)
            if (
                self.samples
                and sum(a * b for a, b in zip(vector, self.samples[0])) < self.config["threshold"]
            ):
                return {
                    "accepted": False,
                    "count": len(self.samples),
                    "reason": "Face differs from the first sample; restart if necessary",
                }
            if self.enrollment_target:
                target = self.store.gallery(self.config["model_version"]).get(
                    self.enrollment_target, []
                )
                if (
                    not target
                    or max(sum(a * b for a, b in zip(vector, v)) for v in target)
                    < self.config["threshold"]
                ):
                    return {
                        "accepted": False,
                        "count": len(self.samples),
                        "reason": "Face does not match the enrolled person",
                    }
            if len(self.samples) >= 10:
                return {
                    "accepted": False,
                    "count": len(self.samples),
                    "reason": "Ten samples captured; save or cancel",
                }
            self.samples.append(vector)
            self.sample_frame, self.sample_time = frame.frame_id, frame.captured_at
            return {
                "accepted": True,
                "count": len(self.samples),
                "reason": "Accepted. Vary head angle modestly for the next sample.",
            }

    def finish_enrollment(self, name, relationship, note, pronunciation):
        with self.lock:
            self._expire_enrollment()
            if not self.enrollment or len(self.samples) != 10:
                raise ValueError("Ten accepted samples required")
            if self.enrollment_target:
                person_id = self.enrollment_target
                self.store.add_samples(person_id, self.samples, self.config["model_version"])
            else:
                person_id = self.store.enroll(
                    name,
                    relationship,
                    note,
                    pronunciation,
                    self.samples,
                    self.config["model_version"],
                )
            self.cancel_enrollment()
            self.reload_gallery()
            return person_id

    def cancel_enrollment(self):
        with self.lock:
            self.samples = []
            self.enrollment = False
            self.enrollment_target = None

    def clear_history(self):
        with self.lock:
            self.store.clear_history()
            self.previous.clear()
            self.encounter_last.clear()

    def reload_gallery(self):
        revision = self.store.revision
        if revision != self.gallery_revision:
            self.gallery = Gallery(
                self.store.gallery(self.config["model_version"]),
                self.config["threshold"],
                self.config["margin"],
            )
            self.gallery_revision = revision

    def run(self):
        started = False
        retry_at = 0.0
        if self.audio:
            self.audio.start()
        while not self.stopping.is_set():
            tick = time.monotonic()
            try:
                with self.lock:
                    self.now = tick
                    self._expire_enrollment()
                    self.reload_gallery()
                    self.store.people()  # Ensure storage recovered before processing.
                    self.health["storage"] = "ready"
                    paused = self.paused or self.enrollment
                if not started:
                    if tick < retry_at:
                        self.stopping.wait(0.2)
                        continue
                    self.vision.start()
                    started = True
                    self.on_health("camera", "ready")
                if paused:
                    self.stopping.wait(0.2)
                    continue
                frame = self.vision.read()
                if time.monotonic() - frame.captured_at > 1:
                    self.observe([], time.monotonic(), clock_utc())
                    continue
                with self.lock:
                    if self.paused or self.enrollment:
                        continue
                    observations = self.vision.detect(frame.image)
                    detections = [
                        (bbox, self.gallery.match(vector)) for bbox, vector in observations
                    ]
                    self.observe(detections, time.monotonic(), frame.utc)
                self.on_health("camera", "ready")
            except sqlite3.Error:
                self.on_health("storage", "unavailable")
                with self.lock:
                    self.now = time.monotonic()
                    self._reset_presence()
                LOG.warning("Storage unavailable; recognition suspended until retry")
                self.stopping.wait(5)
            except Exception as exc:
                LOG.warning("Runtime iteration failed (%s)", type(exc).__name__)
                self.on_health("camera", "unavailable")
                with self.lock:
                    self.now = time.monotonic()
                    self._reset_presence()
                try:
                    self.vision.close()
                except Exception:
                    pass
                started = False
                retry_at = time.monotonic() + 5
            self.stopping.wait(max(0.0, 0.2 - (time.monotonic() - tick)))
        if self.audio:
            self.audio.close()
        if self.vision:
            self.vision.close()
        with self.lock:
            self._reset_presence()

    def close(self):
        self.stopping.set()
