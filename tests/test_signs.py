import tempfile
import unittest
from pathlib import Path

from cognisight.signs import Navigator, SignStore, the
from cognisight.voice import parse_command


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def house(path):
    """Bedroom -> Hallway -> Bathroom, Hallway -> Kitchen, and back."""
    store = SignStore(path)
    bedroom = store.create("Bedroom")["id"]
    hallway = store.create("Hallway", aliases="corridor")["id"]
    bathroom = store.create("Bathroom", aliases=["toilet", "washroom"])["id"]
    kitchen = store.create("Kitchen", note="Tea is by the window.", say_note=True)["id"]
    store.set_links(bedroom, [{"to": hallway, "text": "Go out of this door and turn left."}])
    store.set_links(
        hallway,
        [
            {"to": bathroom, "text": "The bathroom is the second door on your right."},
            {"to": kitchen, "text": "The kitchen is straight ahead."},
            {"to": bedroom, "text": "Your bedroom is the first door on the left."},
        ],
    )
    store.set_links(kitchen, [{"to": hallway, "text": "Go back through this door."}])
    return store, bedroom, hallway, bathroom, kitchen


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "signs.json"
        self.store, self.bedroom, self.hallway, self.bathroom, self.kitchen = house(self.path)

    def tearDown(self):
        self.directory.cleanup()

    def test_marker_ids_are_the_lowest_free_numbers_and_survive_restart(self):
        self.assertEqual([self.bedroom, self.hallway, self.bathroom, self.kitchen], [0, 1, 2, 3])
        self.store.delete(self.hallway)
        self.assertEqual(self.store.create("Study")["id"], 1)
        again = SignStore(self.path)
        self.assertEqual({s["name"] for s in again.signs()}, {"Bedroom", "Bathroom", "Kitchen", "Study"})

    def test_names_are_unique_and_required(self):
        with self.assertRaises(FileExistsError):
            self.store.create("kitchen")
        with self.assertRaises(ValueError):
            self.store.create("   ")

    def test_route_follows_written_directions(self):
        self.assertEqual(self.store.route(self.bedroom, self.bathroom), [self.bedroom, self.hallway, self.bathroom])
        self.assertEqual(self.store.route(self.kitchen, self.bedroom), [self.kitchen, self.hallway, self.bedroom])
        self.assertIsNone(self.store.route(self.bathroom, self.kitchen))  # no way out of the bathroom written

    def test_deleting_a_sign_removes_its_directions_and_plan_place(self):
        self.store.set_plan({"width": 10, "height": 8, "signs": [{"sign": self.hallway, "x": 1, "y": 1, "facing": 90}]})
        self.store.delete(self.hallway)
        self.assertFalse([l for l in self.store.links() if self.hallway in (l["from"], l["to"])])
        self.assertEqual(self.store.plan()["signs"], [])

    def test_links_reject_bad_input(self):
        for bad in ([{"to": self.bedroom, "text": "loop"}], [{"to": 49, "text": "x"}], [{"to": self.kitchen, "text": " "}]):
            with self.assertRaises(ValueError):
                self.store.set_links(self.bedroom, bad)

    def test_plan_is_cleaned_and_clamped(self):
        plan = self.store.set_plan(
            {
                "width": 100,
                "height": "8",
                "walls": [{"x1": -5, "y1": 0, "x2": 70, "y2": "nan"}],
                "doors": [{"x": 3, "y": 0, "angle": 450, "width": 9}],
                "labels": [{"x": 1, "y": 1, "text": "  Kitchen "}, {"x": 1, "y": 1, "text": ""}],
                "signs": [{"sign": self.kitchen, "x": 2, "y": 2, "facing": -90}, {"sign": 49, "x": 1, "y": 1}],
            }
        )
        self.assertEqual(plan["width"], 50)
        self.assertEqual(plan["walls"][0], {"x1": 0, "y1": 0, "x2": 50, "y2": 0})
        self.assertEqual(plan["doors"][0]["angle"], 90)
        self.assertEqual(plan["doors"][0]["width"], 3)
        self.assertEqual([l["text"] for l in plan["labels"]], ["Kitchen"])
        self.assertEqual(plan["signs"], [{"sign": self.kitchen, "x": 2, "y": 2, "facing": 270}])
        with self.assertRaises(ValueError):
            self.store.set_plan({"walls": "nope"})

    def test_spoken_destination(self):
        self.assertEqual(self.store.find_destination("take me to the toilet please")["name"], "Bathroom")
        self.assertEqual(self.store.find_destination("Where's the kitchen?")["name"], "Kitchen")
        self.assertIsNone(self.store.find_destination("take me to the garden"))
        self.assertEqual(parse_command("Take me to the bathroom"), "go")
        self.assertEqual(parse_command("where is the kitchen"), "go")
        self.assertEqual(parse_command("who is this"), "who")

    def test_the(self):
        self.assertEqual(the("Kitchen"), "the kitchen")
        self.assertEqual(the("TV room"), "the TV room")
        self.assertEqual(the("Priya's room"), "Priya's room")
        self.assertEqual(the("The Study"), "the Study")


class NavigatorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store, self.bedroom, self.hallway, self.bathroom, self.kitchen = house(
            Path(self.directory.name) / "signs.json"
        )
        self.clock = Clock()
        self.said = []
        self.events = []
        self.nav = Navigator(self.store, self.said.append, lambda *e: self.events.append(e), self.clock)

    def tearDown(self):
        self.directory.cleanup()

    def test_walking_into_a_room_names_it_once(self):
        self.nav.sighting(self.kitchen)
        self.nav.sighting(self.kitchen)
        self.assertEqual(self.said, ["This is the kitchen. Tea is by the window."])
        self.assertEqual(self.nav.state()["room"]["name"], "Kitchen")
        self.clock.now += 121
        self.nav.sighting(self.kitchen)
        self.assertEqual(len(self.said), 2)

    def test_guided_trip_one_step_per_sign(self):
        self.nav.sighting(self.bedroom)
        self.said.clear()
        guide = self.nav.start(self.bathroom)
        self.assertEqual(self.said, ["Go out of this door and turn left."])
        self.assertEqual(guide["route"], [self.bedroom, self.hallway, self.bathroom])
        self.clock.now += 5
        self.nav.sighting(self.hallway)
        self.assertEqual(self.said[-1], "The bathroom is the second door on your right.")
        self.nav.sighting(self.hallway)  # still standing there: not repeated at once
        self.assertEqual(len(self.said), 2)
        self.clock.now += 31
        self.nav.sighting(self.hallway)  # lingering: repeat the step
        self.assertEqual(len(self.said), 3)
        self.nav.sighting(self.bathroom)
        self.assertEqual(self.said[-1], "You're at the bathroom.")
        arrived = self.nav.state()["guide"]
        self.assertEqual(arrived["at"], self.bathroom)  # shown as arrived for a moment
        self.assertEqual(arrived["route"], [self.bedroom, self.hallway, self.bathroom])
        self.nav.sighting(self.hallway)  # a finished trip gives no more directions
        self.assertEqual(self.said[-1], "You're at the bathroom.")
        self.clock.now += 21
        self.assertIsNone(self.nav.state()["guide"])

    def test_wrong_turn_is_rerouted(self):
        self.nav.start(self.bathroom)
        self.assertIn("Look around for a sign", self.said[-1])
        self.nav.sighting(self.kitchen)
        self.assertEqual(self.said[-1], "Go back through this door.")
        self.assertEqual(self.nav.state()["guide"]["route"], [self.kitchen, self.hallway, self.bathroom])

    def test_going_back_past_a_sign_does_not_repeat_it_in_the_route(self):
        self.nav.sighting(self.bedroom)
        self.nav.start(self.bathroom)
        self.nav.sighting(self.hallway)
        self.nav.sighting(self.kitchen)  # wrong way
        self.nav.sighting(self.hallway)  # back again
        self.assertEqual(self.nav.state()["guide"]["route"], [self.bedroom, self.hallway, self.bathroom])

    def test_rooms_are_not_named_before_speech_works(self):
        quiet = Navigator(self.store, self.said.append, clock=self.clock, can_speak=lambda: False)
        quiet.sighting(self.kitchen)
        self.assertEqual(self.said, [])
        loud = Navigator(self.store, self.said.append, clock=self.clock)
        loud.sighting(self.kitchen)
        self.assertEqual(len(self.said), 1)

    def test_staying_in_a_room_names_it_once(self):
        for _ in range(20):
            self.nav.sighting(self.kitchen)
            self.clock.now += 30
        self.assertEqual(len(self.said), 1)

    def test_no_route_is_said_plainly(self):
        self.nav.start(self.kitchen)
        self.nav.sighting(self.bathroom)
        self.assertEqual(self.said[-1], "I don't know the way to the kitchen from here.")

    def test_old_sighting_does_not_count_as_here(self):
        self.nav.sighting(self.bedroom)
        self.clock.now += 300
        self.nav.start(self.bathroom)
        self.assertIn("Look around for a sign", self.said[-1])

    def test_unknown_marker_is_ignored(self):
        self.nav.sighting(42)
        self.assertIsNone(self.nav.state()["room"])


class DetectionTests(unittest.TestCase):
    def test_printed_marker_is_read_and_far_ones_ignored(self):
        try:
            import cv2
            import numpy as np

            from cognisight.signs import MarkerDetector
        except ImportError:
            self.skipTest("OpenCV is not installed")
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        frame = np.full((480, 640, 3), 255, np.uint8)
        near = cv2.aruco.generateImageMarker(dictionary, 5, 120)
        far = cv2.aruco.generateImageMarker(dictionary, 9, 18)
        frame[100:220, 100:220] = near[:, :, None]
        frame[300:318, 400:418] = far[:, :, None]
        found = MarkerDetector().detect(frame)
        self.assertEqual([marker_id for marker_id, _ in found], [5])


if __name__ == "__main__":
    unittest.main()
