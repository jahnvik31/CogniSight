import math
import tempfile
import unittest
from pathlib import Path

from cognisight.recognition.store import Store
from cognisight.recognition.matching import Gallery, Match
from cognisight.recognition.tracking import Tracker
from cognisight.recognition.commands import parse_command


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "state.sqlite3")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_profiles_embeddings_history_and_delete_survive_restart(self):
        p = self.store.enroll(
            "Ananya", "your daughter", "Enjoys gardening", "", [[1, 0]] * 10, "sface-v1"
        )
        self.assertEqual(self.store.gallery("sface-v1")[p][0], (1.0, 0.0))
        self.assertIsNone(self.store.start_encounter(p, 1000))
        self.store.end_encounter(p, 1020)
        self.assertEqual(self.store.start_encounter(p, 1100), 1000)
        self.store.close()
        self.store = Store(Path(self.temp.name) / "state.sqlite3")
        self.assertEqual(self.store.person(p)["relationship"], "your daughter")
        self.store.delete(p)
        self.assertEqual(self.store.gallery("sface-v1"), {})
        self.assertEqual(self.store.encounter_count(), 0)

    def test_invalid_enrollment_is_atomic_and_capacity_enforced(self):
        for vectors in ([[1, 0]] * 9, [[0, 0]] * 10, [[math.nan, 0]] * 10, [[1, 0], [1, 0, 0]] * 5):
            with self.assertRaises(ValueError):
                self.store.enroll("A", "", "", "", vectors, "v1")
        self.assertEqual(self.store.people(), [])
        self.store.capacity = 1
        self.store.enroll("Same", "", "", "", [[1, 0]] * 10, "v1")
        with self.assertRaises(ValueError):
            self.store.enroll("Same", "", "", "", [[0, 1]] * 10, "v1")

    def test_disabled_and_wrong_model_never_enter_gallery(self):
        p = self.store.enroll("A", "", "", "", [[1, 0]] * 10, "v1")
        self.assertEqual(self.store.gallery("v2"), {})
        self.store.update(p, "A", "", "", "", False)
        self.assertEqual(self.store.gallery("v1"), {})

    def test_history_retention_and_unreliable_clock(self):
        p = self.store.enroll("A", "", "", "", [[1, 0]] * 10, "v1")
        self.store.start_encounter(p, None)
        self.assertEqual(self.store.encounter_count(), 0)
        self.store.start_encounter(p, 1)
        self.store.end_encounter(p, 2)
        self.store.prune(40 * 86400)
        self.assertEqual(self.store.encounter_count(), 0)


class MatchingTests(unittest.TestCase):
    def test_best_match_unknown_and_margin(self):
        g = Gallery({"a": [(1, 0)], "b": [(0, 1)]}, threshold=0.8, margin=0.1)
        self.assertEqual(g.match([1, 0]).person_id, "a")
        self.assertEqual(g.match([-1, 0]).state, "unknown")
        self.assertEqual(g.match([1, 1]).state, "unknown")
        g = Gallery({"a": [(1, 0)], "b": [(1, 0.01)]}, threshold=0.8, margin=0.1)
        self.assertEqual(g.match([1, 0]).state, "ambiguous")

    def test_invalid_vectors_fail_closed_and_empty_gallery(self):
        g = Gallery({"a": [(1, 0)]}, 0.8, 0.1)
        for value in ([0, 0], [math.inf, 0], [1, 2, 3]):
            self.assertEqual(g.match(value).state, "unknown")
        self.assertEqual(Gallery({}, 0.8, 0.1).match([1, 0]).state, "unknown")


class TrackingTests(unittest.TestCase):
    def test_confirmation_cooldown_loss_and_identity_change(self):
        t = Tracker()
        known = Match("known", "a", 0.9)
        for now in (0, 0.2):
            self.assertEqual(t.update([((0, 0, 100, 100), known)], now), [])
        events = t.update([((0, 0, 100, 100), known)], 0.4)
        self.assertEqual([e.kind for e in events], ["confirmed"])
        self.assertTrue(t.should_announce("a", 0.4))
        self.assertFalse(t.should_announce("a", 10))
        t.update([], 1)
        self.assertEqual(t.visible(11), [])
        self.assertEqual([e.kind for e in t.update([], 11)], ["lost"])
        self.assertTrue(t.should_announce("a", 61))

    def test_unknown_resets_confirmation(self):
        t = Tracker()
        k = Match("known", "a", 0.9)
        u = Match("unknown", None, 0.2)
        t.update([((0, 0, 100, 100), k)], 0)
        t.update([((0, 0, 100, 100), u)], 0.2)
        self.assertEqual(t.update([((0, 0, 100, 100), k)], 0.4), [])

    def test_multiple_people_and_ambiguous_primary(self):
        t = Tracker()
        faces = [
            ((100, 100, 100, 100), Match("known", "a", 0.9)),
            ((440, 100, 100, 100), Match("known", "b", 0.9)),
        ]
        for now in (0, 0.2, 0.4):
            t.update(faces, now)
        self.assertIsNone(t.primary(0.5, 640, 480))
        self.assertEqual(len(t.visible(0.5)), 2)


class CommandTests(unittest.TestCase):
    def test_prefix_required_and_unknown_speech_rejected(self):
        self.assertEqual(parse_command("Cogni, who is this?"), "identify")
        self.assertEqual(parse_command("cogni stop"), "stop")
        self.assertIsNone(parse_command("please stop"))
        self.assertIsNone(parse_command("cogni [unk] who is this"))
        self.assertIsNone(parse_command("cogni who is this tomorrow"))
