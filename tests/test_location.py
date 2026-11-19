import unittest

from cognisight.location import Locator, lookup, parse_nmcli

NMCLI = "\n".join(
    [
        r"AA\:BB\:CC\:DD\:EE\:01:80:6",
        r"AA\:BB\:CC\:DD\:EE\:02:40:149",
        r"AA\:BB\:CC\:DD\:EE\:01:60:6",
        r"garbage line",
        "",
    ]
)


class LocationTests(unittest.TestCase):
    def test_parse_nmcli_unescapes_and_dedupes(self):
        points = parse_nmcli(NMCLI)
        self.assertEqual(len(points), 2)
        first = [p for p in points if p["macAddress"] == "aa:bb:cc:dd:ee:01"][0]
        self.assertEqual(first["signalStrength"], -60)  # strongest reading kept
        self.assertEqual(first["channel"], 6)

    def test_no_key_is_not_configured(self):
        result = lookup("", [], post=lambda *_: self.fail("must not call Google"))
        self.assertEqual(result["status"], "not_configured")

    def test_two_access_points_are_sent_as_wifi(self):
        sent = {}

        def post(url, body):
            sent.update(body)
            return 200, {"location": {"lat": 16.5, "lng": 80.5}, "accuracy": 35}

        result = lookup("key", parse_nmcli(NMCLI), post=post)
        self.assertEqual(len(sent["wifiAccessPoints"]), 2)
        self.assertTrue(sent["considerIp"])
        self.assertEqual(result["source"], "wifi")
        self.assertEqual(result["accuracy"], 35)

    def test_one_access_point_falls_back_to_internet_address(self):
        sent = {}

        def post(url, body):
            sent.update(body)
            return 200, {"location": {"lat": 16.5, "lng": 80.5}, "accuracy": 2700}

        result = lookup("key", parse_nmcli(NMCLI.splitlines()[0]), post=post)
        self.assertNotIn("wifiAccessPoints", sent)
        self.assertEqual(result["source"], "ip")

    def test_wide_answer_is_labelled_ip_even_with_wifi(self):
        post = lambda url, body: (200, {"location": {"lat": 1, "lng": 2}, "accuracy": 2700})
        self.assertEqual(lookup("key", parse_nmcli(NMCLI), post=post)["source"], "ip")

    def test_google_error_is_reported(self):
        post = lambda url, body: (404, {"error": {"message": "Not Found"}})
        result = lookup("key", [], post=post)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "Not Found")

    def test_locator_caches_until_forced(self):
        calls = []

        def post(url, body):
            calls.append(body)
            return 200, {"location": {"lat": 1, "lng": 2}, "accuracy": 10}

        locator = Locator("key", scan=lambda: [], post=post, clock=lambda: 100.0)
        locator.current()
        locator.current()
        self.assertEqual(len(calls), 1)
        locator.current(force=True)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
