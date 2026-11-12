import unittest
from unittest.mock import patch
from cognisight.recognition.types import clock_utc


class ClockTests(unittest.TestCase):
    def test_unsynchronized_clock_is_not_used_for_encounters(self):
        with (
            patch("time.time", return_value=2000000000),
            patch("pathlib.Path.exists", return_value=False),
        ):
            self.assertIsNone(clock_utc())

    def test_synchronized_sane_clock_accepted(self):
        with (
            patch("time.time", return_value=2000000000),
            patch("pathlib.Path.exists", return_value=True),
        ):
            self.assertEqual(clock_utc(), 2000000000)

    def test_synchronized_but_reset_clock_rejected(self):
        with patch("time.time", return_value=0), patch("pathlib.Path.exists", return_value=True):
            self.assertIsNone(clock_utc())
