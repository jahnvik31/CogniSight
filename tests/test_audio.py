"""Audio policy tests run without microphone, synthesizer, or third-party imports."""

import threading
import unittest
from unittest.mock import patch

from cognisight.recognition.audio import (
    AudioEngine,
    SpeechQueue,
    select_usb_device,
    validate_grammar,
)


class DeviceTests(unittest.TestCase):
    devices = [
        {"name": "Built-in Speaker", "max_input_channels": 0, "max_output_channels": 2},
        {"name": "USB Headset", "max_input_channels": 1, "max_output_channels": 2},
        {"name": "USB Headset Other", "max_input_channels": 1, "max_output_channels": 2},
    ]

    def test_requires_specific_usb_route_and_correct_direction(self):
        self.assertEqual(select_usb_device(self.devices, "USB Headset", "input"), 1)
        for name in ("", "Built-in Speaker", "Headset", "USB Missing"):
            with self.assertRaises(ValueError):
                select_usb_device(self.devices, name, "output")
        with self.assertRaises(ValueError):
            select_usb_device([self.devices[1], self.devices[1]], "USB Headset", "input")
        with self.assertRaises(ValueError):
            select_usb_device(
                [{"name": "USB Output", "max_input_channels": 0}], "USB Output", "input"
            )


class VocabularyTests(unittest.TestCase):
    def test_missing_prefix_is_rejected_instead_of_silently_ignored(self):
        class Vocabulary:
            def vosk_model_find_word(self, word):
                return {"who": 1, "is": 2, "this": 3}.get(word, -1)

        with self.assertRaises(ValueError):
            validate_grammar(Vocabulary(), ("cogni who is this", "[unk]"))
        validate_grammar(Vocabulary(), ("who is this", "[unk]"))


class QueueTests(unittest.TestCase):
    def test_priority_deduplication_and_bounded_backpressure(self):
        q = SpeechQueue(2)
        self.assertTrue(q.put("automatic", lambda: True, 0, 0))
        self.assertFalse(q.put("automatic", lambda: True, 0, 0))
        self.assertTrue(q.put("requested", lambda: True, 10, 0))
        self.assertFalse(q.put("extra automatic", lambda: True, 0, 0))
        self.assertEqual(q.get(0.01).text, "requested")
        self.assertEqual(q.get(0.01).text, "automatic")
        self.assertIsNone(q.get(0.01))

    def test_equal_priority_is_fifo_and_explicit_eviction_keeps_older_automatic(self):
        q = SpeechQueue(3)
        for text in ("first", "second", "third"):
            self.assertTrue(q.put(text, lambda: True, 0, 0))
        self.assertTrue(q.put("explicit", lambda: True, 1, 0))
        self.assertEqual([q.get(0.01).text for _ in range(3)],
                         ["explicit", "first", "second"])

    def test_requested_speech_replaces_low_priority_and_clear_drops_pending(self):
        q = SpeechQueue(1)
        q.put("automatic", lambda: True, 0, 0)
        self.assertTrue(q.put("request", lambda: True, 10, 0))
        self.assertEqual(q.get(0.01).text, "request")
        q.put("pending", lambda: True, 0, 0)
        q.clear()
        self.assertIsNone(q.get(0.01))


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.commands = []
        self.health = []
        self.engine = AudioEngine({}, self.commands.append, lambda *x: self.health.append(x))

    def tearDown(self):
        self.engine.close()

    def test_cancel_invalidates_inflight_and_pending_speech(self):
        self.engine._available.set()
        self.assertTrue(self.engine.say("Ananya is here"))
        before = self.engine._generation
        self.engine.cancel()
        self.assertGreater(self.engine._generation, before)
        self.assertIsNone(self.engine._speech.get(0.01))

    def test_expired_or_self_triggering_utterance_never_queued(self):
        self.engine._available.set()
        self.assertFalse(self.engine.say("stale person", valid=lambda: False))
        self.assertFalse(self.engine.say("Please say Cogni, stop to cancel"))
        self.assertIsNone(self.engine._speech.get(0.01))

    def test_visibility_and_generation_rechecked_after_queueing(self):
        self.engine._available.set()
        visible = [True]
        self.assertTrue(self.engine.say("Ananya", valid=lambda: visible[0]))
        item = self.engine._speech.get(0.01)
        self.assertTrue(self.engine._item_valid(item))
        visible[0] = False
        self.assertFalse(self.engine._item_valid(item))
        visible[0] = True
        self.engine.cancel()
        self.assertFalse(self.engine._item_valid(item))

    def test_only_stop_is_dispatched_during_playback(self):
        self.engine._speaking.set()
        self.engine._dispatch("cogni who is this")
        self.assertEqual(self.commands, [])
        self.engine._dispatch("cogni stop")
        self.assertEqual(self.commands, ["stop"])
        self.engine._speaking.clear()
        self.engine._dispatch("unrelated speech")
        self.engine._dispatch("computer who is this")
        self.assertEqual(self.commands, ["stop", "identify"])

    def test_output_fault_closes_old_microphone_before_reconnect(self):
        class InputStream:
            def __init__(self):
                self.closes = 0

            def close(self):
                self.closes += 1

            def abort(self):
                pass

        class FailingVoice:
            def synthesize(self, text):
                raise OSError("Native synthesis/output failure")

        old_stream = InputStream()
        self.engine._stream = old_stream
        self.engine._voice = FailingVoice()
        self.engine._available.set()
        fault = threading.Event()
        self.engine.on_health = lambda *args: fault.set()
        self.assertTrue(self.engine.say("Ananya"))
        speech_worker = threading.Thread(target=self.engine._speak)
        speech_worker.start()
        self.assertTrue(fault.wait(1))
        observed = []

        def reconnect():
            observed.append(old_stream.closes)
            self.engine._stop.set()

        try:
            with patch.object(self.engine, "_connect", side_effect=reconnect):
                self.engine._listen()
        finally:
            self.engine._stop.set()
            speech_worker.join(1)
        self.assertEqual(observed, [1])
        self.assertEqual(old_stream.closes, 1)

    def test_stuck_worker_remains_owned_and_prevents_restart(self):
        # A native worker may ignore stop. Never forget it and open another route.
        class StuckWorker:
            def join(self, timeout):
                pass

            def is_alive(self):
                return True

        worker = StuckWorker()
        self.engine._threads = [worker]
        try:
            with self.assertRaisesRegex(RuntimeError, "Audio worker failed to stop"):
                self.engine.close()
            self.assertEqual(self.engine._threads, [worker])
            with patch("cognisight.recognition.audio.threading.Thread") as factory:
                self.engine.start()
                factory.assert_not_called()
        finally:
            self.engine._threads = []

    def test_expiry_during_synthesis_never_opens_output(self):
        visible = [True]
        engine = self.engine

        class Voice:
            def synthesize(self, text):
                visible[0] = False
                engine._stop.set()
                yield object()

        engine._voice = Voice()
        engine._available.set()
        self.assertTrue(engine.say("Example person", valid=lambda: visible[0]))
        with patch.object(engine, "_check_routes") as routes:
            engine._speak()
            routes.assert_not_called()
        self.assertFalse(engine.speaking)

    def test_unavailable_output_does_not_queue_private_speech(self):
        self.assertFalse(self.engine.available)
        self.assertFalse(self.engine.say("private", priority=1))
        self.assertIsNone(self.engine._speech.get(0.01))


if __name__ == "__main__":
    unittest.main()
