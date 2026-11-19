import unittest

from cognisight.faces import Person
from cognisight.voice import Announcer, introduction, parse_command


class FakeSpeaker:
    available = True
    error = None

    def __init__(self, fail=False):
        self.said = []
        self.stopped = 0
        self.fail = fail

    def say(self, text):
        if self.fail:
            raise OSError("no output device")
        self.said.append(text)

    def stop(self):
        self.stopped += 1


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class AnnouncerTests(unittest.TestCase):
    def setUp(self):
        self.speaker = FakeSpeaker()
        self.clock = Clock()
        self.said = []
        self.announcer = Announcer(self.speaker, cooldown=120, clock=self.clock, on_said=self.said.append)

    def test_introduction_wording(self):
        self.assertEqual(introduction("Priya", "daughter"), "This is Priya, your daughter.")
        self.assertEqual(introduction("Priya", ""), "This is Priya.")
        self.assertEqual(introduction("Ravi", "my neighbour"), "This is Ravi, your neighbour.")
        self.assertEqual(introduction("Dr Rao", "the family doctor"), "This is Dr Rao, the family doctor.")

    def test_speaks_at_once_then_waits_out_the_cooldown(self):
        self.assertEqual(self.announcer.seen("Priya", "daughter"), "This is Priya, your daughter.")
        self.clock.now += 60
        self.assertIsNone(self.announcer.seen("Priya", "daughter"))
        self.assertEqual(self.announcer.seen("Ravi"), "This is Ravi.")
        self.clock.now += 61
        self.assertIsNotNone(self.announcer.seen("Priya", "daughter"))
        self.assertEqual(len(self.speaker.said), 3)
        self.assertEqual(self.said, self.speaker.said)

    def test_muted_says_nothing_and_introduces_after_unmute(self):
        self.announcer.enabled = False
        self.assertIsNone(self.announcer.seen("Priya"))
        self.announcer.enabled = True
        self.assertEqual(self.announcer.seen("Priya"), "This is Priya.")

    def test_audio_failure_is_reported_not_raised(self):
        announcer = Announcer(FakeSpeaker(fail=True), clock=self.clock)
        announcer.seen("Priya")
        self.assertIn("no output device", announcer.error)

    def test_commands(self):
        self.assertEqual(parse_command("Stop."), "stop")
        self.assertEqual(parse_command("okay be quiet"), "stop")
        self.assertEqual(parse_command("Who is this?"), "who")
        self.assertEqual(parse_command("who's that"), "who")
        self.assertEqual(parse_command("tell me more"), "more")
        self.assertIsNone(parse_command("This is Priya, your daughter."))
        self.assertIsNone(parse_command(""))

    def test_handle_who_and_more_and_stop(self):
        priya = Person("Priya", "daughter", "Visits on Sundays.", ["a.jpg"])
        self.announcer.handle("who is this", [priya])
        self.announcer.handle("tell me more", [priya])
        self.announcer.handle("who is this", [])
        self.announcer.handle("stop", [])
        self.assertEqual(
            self.speaker.said,
            ["This is Priya, your daughter.", "Visits on Sundays.", "I don't see anyone I know right now."],
        )
        self.assertEqual(self.speaker.stopped, 1)


if __name__ == "__main__":
    unittest.main()
