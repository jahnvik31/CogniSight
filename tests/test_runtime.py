import tempfile
import unittest
from pathlib import Path
from cognisight.recognition.store import Store
from cognisight.recognition.runtime import Runtime
from cognisight.recognition.matching import Match
from cognisight.recognition.config import validate_config


class Audio:
    available = True
    speaking = False

    def __init__(self):
        self.messages = []
        self.cancelled = False

    def say(self, text, valid=lambda: True, priority=0):
        if valid():
            self.messages.append((text, valid, priority))
            return True
        return False

    def cancel(self):
        self.cancelled = True

    def close(self):
        pass


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "db")
        self.p = self.store.enroll(
            "Ananya", "your daughter", "Enjoys gardening", "", [[1, 0]] * 10, "v1"
        )
        self.audio = Audio()
        self.runtime = Runtime(
            self.store,
            {
                "model_version": "v1",
                "threshold": 0.8,
                "margin": 0.1,
                "calibrated": True,
            },
            audio=self.audio,
            clock=lambda: self.runtime.now,
        )

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def confirm(self, now=0):
        for delta in (0, 0.2, 0.4):
            self.runtime.observe(
                [((0, 0, 100, 100), Match("known", self.p, 0.99))],
                now + delta,
                2000000000 + now + delta,
            )

    def test_auto_context_and_request_expiry(self):
        self.confirm()
        self.assertIn("Ananya", self.audio.messages[-1][0])
        self.runtime.command("context", now=0.5)
        self.assertIn("Enjoys gardening", self.audio.messages[-1][0])
        valid = self.audio.messages[-1][1]
        self.runtime.observe([], 11, 2000000011)
        self.assertFalse(valid())
        self.runtime.command("context", now=11)
        self.assertNotIn("Enjoys gardening", self.audio.messages[-1][0])

    def test_pause_and_stop_cancel_without_resume_side_effect(self):
        self.confirm()
        self.runtime.command("pause", now=0.5)
        self.assertTrue(self.runtime.paused)
        self.assertEqual(self.runtime.tracker.visible(0.5), [])
        self.runtime.command("stop", now=0.6)
        self.assertTrue(self.audio.cancelled)
        self.assertTrue(self.runtime.paused)

    def test_history_is_previous_encounter_not_current(self):
        self.confirm()
        self.runtime.observe([], 11, 2000000011)
        self.confirm(20)
        self.runtime.command("history", now=21)
        self.assertIn("previous", self.audio.messages[-1][0].lower())

    def test_disable_profile_invalidates_queued_context(self):
        self.confirm()
        valid = self.audio.messages[-1][1]
        self.store.update(self.p, "Ananya", "", "", "", False)
        self.assertFalse(valid())

    def test_uncalibrated_runtime_never_announces_identity(self):
        self.runtime.config["calibrated"] = False
        self.confirm()
        self.assertEqual(self.audio.messages, [])

    def test_enrollment_prevents_mixed_person_samples(self):
        class Camera:
            n = 0

            def read(self):
                from cognisight.recognition.types import FramePacket

                self.n += 1
                return FramePacket(self.n, self.n, None, None)

            def enrollment_sample(self, image):
                return ([1, 0] if self.n == 1 else [0, 1]), ""

        self.runtime.vision = Camera()
        self.runtime.begin_enrollment()
        self.assertTrue(self.runtime.capture_sample()["accepted"])
        self.assertFalse(self.runtime.capture_sample()["accepted"])
        self.runtime.cancel_enrollment()
        with self.assertRaises(ValueError):
            self.runtime.finish_enrollment("X", "", "", "")


class ConfigTests(unittest.TestCase):
    def test_invalid_threshold_devices_and_memory_limits_rejected(self):
        base = dict(
            model_version="v1",
            threshold=0.8,
            margin=0.1,
            input_device="USB Mic",
            output_device="USB Headset",
            calibrated=False,
        )
        self.assertEqual(validate_config(base)["threshold"], 0.8)
        for change in (
            {"threshold": 0},
            {"margin": 0},
            {"input_device": ""},
            {"output_device": "default"},
            {"calibrated": "yes"},
        ):
            with self.assertRaises(ValueError):
                validate_config(dict(base, **change))


class AdditionalRuntimeTests(unittest.TestCase):
    setUp = RuntimeTests.setUp
    tearDown = RuntimeTests.tearDown
    confirm = RuntimeTests.confirm

    def test_edited_profile_invalidates_old_queued_speech(self):
        self.confirm()
        valid = self.audio.messages[-1][1]
        self.store.update(
            self.p, "Different name", "different relationship", "", "", True
        )
        self.assertFalse(valid())

    def test_presence_reset_preserves_announcement_cooldown(self):
        self.confirm()
        count = len(self.audio.messages)
        self.runtime._reset_presence()
        self.confirm(1)
        self.assertEqual(len(self.audio.messages), count)

    def test_unreliable_clock_does_not_fake_history(self):
        for now in (0, 0.2, 0.4):
            self.runtime.observe(
                [((0, 0, 100, 100), Match("known", self.p, 0.99))], now, None
            )
        self.runtime.command("history", now=0.5)
        self.assertIn("unreliable", self.audio.messages[-1][0])


class RecoveryTests(unittest.TestCase):
    setUp = RuntimeTests.setUp
    tearDown = RuntimeTests.tearDown
    confirm = RuntimeTests.confirm

    def test_unknown_foreground_blocks_background_identity_request(self):
        for now in (0, 0.2, 0.4):
            self.runtime.observe(
                [
                    ((250, 100, 150, 180), Match("unknown", None, 0.1)),
                    ((0, 0, 60, 70), Match("known", self.p, 0.99)),
                ],
                now,
                None,
            )
        self.runtime.command("identify", now=0.5)
        self.assertNotIn("Ananya", self.audio.messages[-1][0])

    def test_announces_when_audio_becomes_available_after_confirmation(self):
        self.audio.available = False
        self.confirm()
        self.assertEqual(len(self.audio.messages), 0)
        self.audio.available = True
        self.runtime.observe(
            [((0, 0, 100, 100), Match("known", self.p, 0.99))], 0.6, None
        )
        self.assertEqual(len(self.audio.messages), 1)

    def test_storage_failure_during_reset_does_not_kill_runtime(self):
        import sqlite3
        from unittest.mock import patch

        self.confirm()
        with patch.object(
            self.store,
            "end_encounter",
            side_effect=sqlite3.OperationalError("disk full"),
        ):
            self.runtime._reset_presence()
        self.assertEqual(self.runtime.health["storage"], "unavailable")
        self.assertEqual(self.runtime.encounter_last, {})
