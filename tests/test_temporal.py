"""Dropouts cannot manufacture consecutive observations or continuous encounters."""

import unittest
import test_runtime as runtime_tests
from cognisight.recognition.matching import Match
from cognisight.recognition.tracking import Tracker


class TemporalTests(unittest.TestCase):
    setUp = runtime_tests.RuntimeTests.setUp
    tearDown = runtime_tests.RuntimeTests.tearDown
    confirm = runtime_tests.RuntimeTests.confirm

    def test_three_observations_must_be_temporally_consecutive(self):
        tracker = Tracker()
        face = [((0, 0, 100, 100), Match("known", "person", 0.99))]
        tracker.update(face, 0)
        tracker.update(face, 0.2)
        tracker.update(face, 5)
        self.assertEqual(tracker.visible(5), [])
        tracker.update(face, 5.2)
        tracker.update(face, 5.4)
        self.assertEqual(len(tracker.visible(5.4)), 1)

    def test_return_after_gap_requires_reconfirmation_and_new_encounter(self):
        self.confirm()
        events = self.runtime.subscribe()
        self.runtime.observe(
            [((0, 0, 100, 100), Match("known", self.p, 0.99))], 20, 2000000020
        )
        self.assertEqual(self.runtime.tracker.visible(20), [])
        self.assertEqual(events.get_nowait()["kind"], "lost")
        for now in (20.2, 20.4):
            self.runtime.observe(
                [((0, 0, 100, 100), Match("known", self.p, 0.99))],
                now,
                2000000000 + now,
            )
        self.assertEqual(self.store.encounter_count(), 2)
        self.assertEqual(self.runtime.previous[self.p], 2000000000.4)

    def test_queued_speech_expires_without_a_new_camera_observation(self):
        self.confirm()
        valid = self.audio.messages[-1][1]
        self.runtime.clock = lambda: 20
        self.assertFalse(valid())
