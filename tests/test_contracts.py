"""Shared boundaries retain identity, evidence age and reader isolation."""

import threading
import unittest
from unittest.mock import patch

import test_runtime as runtime_tests
from cognisight.recognition.types import RecognitionEvent, FramePacket
from cognisight.recognition.tracking import TrackEvent


class EventTests(unittest.TestCase):
    def test_event_identity_is_stable_across_serialization(self):
        event = RecognitionEvent("confirmed", 1, "synthetic-person", None, "v1")
        self.assertTrue(event.event_id)
        self.assertEqual(event.to_dict()["event_id"], event.to_dict()["event_id"])

    def test_malformed_event_is_rejected(self):
        for change in ({"schema_version": 2}, {"schema_version": 1.0}, {"timestamp": float("nan")},
                       {"kind": "invented"}, {"track_id": 0}, {"person_id": ""}):
            fields = dict(kind="confirmed", track_id=1, person_id="synthetic", timestamp=None,
                          model_version="v1")
            with self.subTest(change=change), self.assertRaises(ValueError):
                RecognitionEvent(**dict(fields, **change))


class BoundaryTests(unittest.TestCase):
    setUp = runtime_tests.RuntimeTests.setUp
    tearDown = runtime_tests.RuntimeTests.tearDown
    confirm = runtime_tests.RuntimeTests.confirm

    def test_subscribers_cannot_mutate_each_others_events(self):
        first, second = self.runtime.subscribe(), self.runtime.subscribe()
        self.runtime._publish(TrackEvent("confirmed", 1, self.p))
        original = first.get_nowait()
        other = second.get_nowait()
        self.assertEqual(original["event_id"], other["event_id"])
        original["person_id"] = "tampered"
        self.assertEqual(other["person_id"], self.p)

    def test_subscriber_overflow_drops_oldest_and_unsubscribe_releases_slot(self):
        channels = [self.runtime.subscribe() for _ in range(8)]
        with self.assertRaises(ValueError):
            self.runtime.subscribe()
        self.runtime.unsubscribe(channels[-1])
        self.runtime.subscribe()
        for track_id in range(1, 66):
            self.runtime._publish(TrackEvent("confirmed", track_id, self.p))
        self.assertEqual(channels[0].qsize(), 64)
        self.assertEqual(channels[0].get_nowait()["track_id"], 2)
        self.assertTrue(channels[-1].empty())

    def test_dashboard_does_not_query_profiles_or_devices(self):
        self.runtime.health["camera"] = "ready"
        self.confirm()
        with patch.object(self.store, "person", side_effect=AssertionError("HTTP queried SQLite")):
            state = self.runtime.dashboard_snapshot()
        self.assertEqual(state["recognition"]["people"][0]["name"], "Ananya")

    def test_profile_revision_invalidates_cached_names_before_next_frame(self):
        self.runtime.health["camera"] = "ready"
        self.confirm()
        self.store.update(self.p, "Changed", "", "", "", True)
        state = self.runtime.dashboard_snapshot()["recognition"]
        self.assertEqual(state["people"], [])
        self.assertEqual(state["status"], "unavailable")

    def test_exact_expiry_boundary_clears_recognition(self):
        self.runtime.health["camera"] = "ready"
        self.confirm(0.1)
        self.runtime.clock = lambda: 1.5
        state = self.runtime.dashboard_snapshot()["recognition"]
        self.assertEqual(state["status"], "stale")
        self.assertEqual(state["people"], [])

    def test_repeated_or_older_observation_does_not_confirm_a_face(self):
        from cognisight.recognition.matching import Match
        face = [((0, 0, 100, 100), Match("known", self.p, 0.99))]
        for now in (1, 1, 0.5):
            self.runtime.observe(face, now, None)
        self.assertEqual(self.runtime.tracker.visible(1), [])
        self.assertEqual(self.runtime.observed_monotonic, 1)

    def test_slow_inference_never_renews_source_age_or_announces(self):
        current = [100.0]
        runtime = self.runtime
        runtime.clock = lambda: current[0]

        class Vision:
            def start(self):
                pass

            def read(self):
                return FramePacket(1, 99.9, None, None)

            def detect(self, image):
                current[0] = 102.0
                runtime.close()
                return [((0, 0, 100, 100), [1, 0])]

            def close(self):
                pass

        runtime.vision = Vision()
        with patch("cognisight.recognition.runtime.time.monotonic", side_effect=lambda: current[0]), \
                patch.object(self.audio, "start", create=True):
            runtime.run()
        self.assertEqual(runtime.observed_monotonic, 99.9)
        self.assertEqual(self.audio.messages, [])
        self.assertEqual(runtime.dashboard_snapshot()["recognition"]["status"], "stale")

    def test_automatic_speech_expires_at_exact_evidence_deadline(self):
        self.confirm(0.1)
        valid = self.audio.messages[-1][1]
        self.runtime.clock = lambda: 1.5
        self.assertFalse(valid())

    def test_blocked_profile_producer_does_not_block_independent_gps(self):
        entered, release, returned = threading.Event(), threading.Event(), threading.Event()
        runtime = self.runtime
        runtime.navigation = type("Navigation", (), {"snapshot": lambda self: {"status": "live"}})()
        original = self.store.person

        def blocked(person_id):
            entered.set()
            release.wait(2)
            return original(person_id)

        def produce():
            self.confirm()

        result = []

        def read():
            result.append(runtime.dashboard_snapshot())
            returned.set()

        with patch.object(self.store, "person", side_effect=blocked):
            producer = threading.Thread(target=produce)
            producer.start()
            self.assertTrue(entered.wait(1))
            reader = threading.Thread(target=read)
            reader.start()
            try:
                self.assertTrue(returned.wait(1), "snapshot waited for blocked profile read")
                self.assertEqual(result[0]["outdoor"]["status"], "live")
                self.assertEqual(result[0]["recognition"]["status"], "unavailable")
            finally:
                release.set()
                producer.join(2)
                reader.join(2)


class LifecycleTests(unittest.TestCase):
    setUp = runtime_tests.RuntimeTests.setUp
    tearDown = runtime_tests.RuntimeTests.tearDown

    def test_failed_audio_shutdown_still_closes_camera_and_clears_presence(self):
        calls = []

        class Audio:
            def start(self):
                pass

            def close(self):
                calls.append("audio")
                raise RuntimeError("worker still alive")

            def cancel(self):
                calls.append("cancel")

        class Vision:
            def close(self):
                calls.append("camera")

        self.runtime.audio = Audio()
        self.runtime.vision = Vision()
        self.runtime.context_person = self.p
        self.runtime.close()
        with self.assertRaises(RuntimeError):
            self.runtime.run()
        self.assertEqual(calls, ["audio", "camera", "cancel"])
        self.assertIsNone(self.runtime.context_person)
        self.assertTrue(self.runtime.cleanup_failed)

    def test_partial_audio_start_failure_attempts_all_owner_cleanup(self):
        calls = []

        class Audio:
            def start(self):
                raise RuntimeError("partial startup")

            def close(self):
                calls.append("audio")

            def cancel(self):
                calls.append("cancel")

        class Vision:
            def close(self):
                calls.append("camera")

        self.runtime.audio = Audio()
        self.runtime.vision = Vision()
        with self.assertRaises(RuntimeError):
            self.runtime.run()
        self.assertEqual(calls, ["audio", "camera", "cancel"])
