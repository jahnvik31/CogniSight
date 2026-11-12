import unittest
import test_runtime as runtime_tests


class BridgeTests(unittest.TestCase):
    setUp = runtime_tests.RuntimeTests.setUp
    tearDown = runtime_tests.RuntimeTests.tearDown
    confirm = runtime_tests.RuntimeTests.confirm

    def test_verified_recognition_and_outdoor_remain_separate(self):
        class Navigation:
            def snapshot(self):
                return {
                    "status": "live",
                    "data_source": "live",
                    "latitude": 0.0,
                    "longitude": 0.0,
                    "age_seconds": 0.0,
                    "observed_at": None,
                }

        self.runtime.navigation = Navigation()
        self.runtime.health["camera"] = "ready"
        self.confirm()
        snapshot = self.runtime.dashboard_snapshot()
        self.assertEqual(snapshot["recognition"]["people"][0]["name"], "Ananya")
        self.assertEqual(snapshot["outdoor"]["latitude"], 0.0)
        self.assertEqual(snapshot["indoor"]["status"], "unavailable")
        self.assertNotIn("embeddings", str(snapshot))

    def test_stale_camera_clears_people_without_hiding_live_gps(self):
        self.runtime.health["camera"] = "ready"
        self.confirm()
        self.runtime.clock = lambda: 20
        state = self.runtime.dashboard_snapshot()
        self.assertEqual(state["recognition"]["status"], "stale")
        self.assertEqual(state["recognition"]["people"], [])
        self.assertEqual(state["outdoor"]["status"], "unavailable")

    def test_disabled_person_and_paused_recognition_never_appear_live(self):
        self.runtime.health["camera"] = "ready"
        self.confirm()
        self.store.update(self.p, "Ananya", "", "", "", False)
        self.assertEqual(self.runtime.dashboard_snapshot()["recognition"]["people"], [])
        self.runtime.command("pause", now=0.5)
        self.assertEqual(self.runtime.dashboard_snapshot()["recognition"]["status"], "paused")

    def test_gps_failure_does_not_remove_recognition_snapshot(self):
        class Navigation:
            def snapshot(self):
                raise RuntimeError("receiver fault")

        self.runtime.navigation = Navigation()
        self.runtime.health["camera"] = "ready"
        self.confirm()
        state = self.runtime.dashboard_snapshot()
        self.assertEqual(state["outdoor"]["status"], "unavailable")
        self.assertEqual(state["recognition"]["status"], "live")

    def test_busy_recognition_does_not_block_independent_gps_snapshot(self):
        import threading
        import time

        class Navigation:
            def snapshot(self):
                return {"status": "live", "data_source": "live", "latitude": 0.0, "longitude": 0.0}

        self.runtime.navigation = Navigation()
        held, release = threading.Event(), threading.Event()

        def hold_detector_lock():
            with self.runtime.lock:
                held.set()
                release.wait(0.5)

        worker = threading.Thread(target=hold_detector_lock)
        worker.start()
        self.assertTrue(held.wait(0.5))
        started = time.monotonic()
        try:
            state = self.runtime.dashboard_snapshot()
            elapsed = time.monotonic() - started
        finally:
            release.set()
            worker.join()
        self.assertLess(elapsed, 0.2)
        self.assertEqual(state["recognition"]["status"], "unavailable")
        self.assertEqual(state["outdoor"]["status"], "live")
