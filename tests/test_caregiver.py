import math
import unittest

from cognisight.caregiver.projection import collect_snapshot
from cognisight.caregiver.security import allowed_request, canonical_hosts


class ProjectionTests(unittest.TestCase):
    def snapshot(self):
        return {
            "schema_version": 1,
            "recognition": {
                "status": "live",
                "data_source": "live",
                "age_seconds": 0.2,
                "observed_at": 2000000000,
                "people": [
                    {
                        "person_id": "p1",
                        "name": "Ananya",
                        "relationship": "your daughter",
                        "note": "Verified note",
                    }
                ],
            },
            "outdoor": {
                "status": "live",
                "data_source": "live",
                "age_seconds": 1,
                "observed_at": None,
                "latitude": 0,
                "longitude": 0,
                "speed_mps": 0,
                "source": "gpsd",
            },
            "indoor": {
                "status": "unavailable",
                "data_source": "unavailable",
                "reason": "not_integrated",
            },
            "health": {"camera": "ready"},
        }

    def test_explicit_valid_origin_zero_coordinates_and_whitelist(self):
        source = self.snapshot()
        source["recognition"]["people"][0]["embedding"] = [1, 2]
        source["health"]["password"] = "secret"
        result = collect_snapshot(source)
        self.assertEqual(result["outdoor"]["latitude"], 0)
        self.assertEqual(result["recognition"]["people"][0]["name"], "Ananya")
        self.assertNotIn("embedding", result["recognition"]["people"][0])
        self.assertNotIn("password", result["health"])

    def test_missing_producer_and_bad_schema_fail_closed(self):
        self.assertEqual(collect_snapshot({})["recognition"]["status"], "unavailable")
        source = self.snapshot()
        source["schema_version"] = 999
        self.assertEqual(collect_snapshot(source)["outdoor"]["status"], "unavailable")

    def test_nonfinite_outofrange_and_nofix_never_live_coordinates(self):
        for changes in (
            {"latitude": math.nan},
            {"longitude": 181},
            {"latitude": True},
            {"status": "no_fix"},
        ):
            source = self.snapshot()
            source["outdoor"].update(changes)
            result = collect_snapshot(source)["outdoor"]
            self.assertIsNone(result["latitude"])
            self.assertIsNone(result["longitude"])
            self.assertNotEqual(result["status"], "live")

    def test_stale_and_unknown_age_hide_person_and_current_fix(self):
        source = self.snapshot()
        source["recognition"]["age_seconds"] = 15
        source["outdoor"]["age_seconds"] = None
        result = collect_snapshot(source)
        self.assertEqual(result["recognition"]["status"], "stale")
        self.assertEqual(result["recognition"]["people"], [])
        self.assertIsNone(result["outdoor"]["latitude"])

    def test_mock_source_cannot_be_labeled_live(self):
        source = self.snapshot()
        source["outdoor"]["data_source"] = "mock"
        result = collect_snapshot(source)
        self.assertTrue(result["has_mock_data"])
        self.assertEqual(result["outdoor"]["data_source"], "mock")
        self.assertEqual(result["outdoor"]["status"], "mock")

    def test_iso_fix_time_and_large_invalid_timestamp(self):
        source = self.snapshot()
        source["outdoor"]["observed_at"] = "2033-05-18T03:33:20Z"
        self.assertEqual(collect_snapshot(source)["outdoor"]["observed_at"], 2000000000)
        source["outdoor"]["observed_at"] = 1e300
        self.assertIsNone(collect_snapshot(source)["outdoor"]["observed_at"])

    def test_no_fix_status_and_historical_location_survive_source_unavailability(self):
        source = self.snapshot()
        source["outdoor"].update(
            status="no_fix",
            data_source="unavailable",
            last_known={
                "latitude": 19.1,
                "longitude": 72.9,
                "observed_at": "2033-05-18T03:33:20Z",
                "age_seconds": 20,
            },
        )
        result = collect_snapshot(source)["outdoor"]
        self.assertEqual(result["status"], "no_fix")
        self.assertIsNone(result["latitude"])
        self.assertEqual(result["last_known"]["latitude"], 19.1)
        self.assertEqual(result["last_known"]["observed_at"], 2000000000)

    def test_producer_expiry_controls_freshness(self):
        for age, expiry, expected in (
            (6, 10, "live"),
            (11, 10, "stale"),
            (3, 2, "stale"),
            (2, 2, "stale"),
        ):
            source = self.snapshot()
            source["outdoor"].update(age_seconds=age, max_age_seconds=expiry)
            self.assertEqual(collect_snapshot(source)["outdoor"]["status"], expected)
        source = self.snapshot()
        source["recognition"]["age_seconds"] = 2
        self.assertEqual(collect_snapshot(source)["recognition"]["status"], "stale")

    def test_malformed_outdoor_does_not_hide_valid_recognition(self):
        source = self.snapshot()
        source["outdoor"].update(data_source=[], status={})
        result = collect_snapshot(source)
        self.assertEqual(result["recognition"]["status"], "live")
        self.assertEqual(result["outdoor"]["status"], "unavailable")


class SecurityTests(unittest.TestCase):
    def test_host_allowlist_and_https_same_origin_required(self):
        hosts = canonical_hosts(["cognisight.local", "192.168.1.20:443"])
        self.assertTrue(allowed_request("cognisight.local", None, "https", hosts, "127.0.0.1"))
        for host, origin, scheme, peer in [
            ("evil.test", None, "https", "127.0.0.1"),
            ("cognisight.local", "https://evil.test", "https", "127.0.0.1"),
            ("cognisight.local", None, "http", "127.0.0.1"),
            ("cognisight.local", None, "https", "192.168.1.1"),
            ("cognisight.local", "null", "https", "127.0.0.1"),
            ("cognisight.local:9999", None, "https", "127.0.0.1"),
        ]:
            self.assertFalse(allowed_request(host, origin, scheme, hosts, peer))
        self.assertTrue(
            allowed_request("192.168.1.20", "https://192.168.1.20", "https", hosts, "127.0.0.1")
        )

    def test_empty_wildcard_and_invalid_hosts_rejected(self):
        for hosts in (
            [],
            ["*"],
            ["http://cognisight.local"],
            ["user@cognisight.local"],
            ["0.0.0.0"],
            ["cognisight.local/path"],
        ):
            with self.assertRaises(ValueError):
                canonical_hosts(hosts)

    def test_bare_config_ipv6_matches_bracketed_request_authority(self):
        hosts = canonical_hosts(["fd00::1"])
        self.assertTrue(
            allowed_request("[fd00::1]", "https://[fd00::1]", "https", hosts, "127.0.0.1")
        )
