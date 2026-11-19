import io
import tempfile
import unittest
from pathlib import Path

from cognisight.faces import Gallery
from cognisight.runtime import CameraUnavailable, Runtime
from cognisight.server import create_app
from test_faces import FakeEmbedder


class NoCamera:
    def __call__(self):
        raise RuntimeError("no camera in tests")


class FakeRuntime(Runtime):
    """A real Runtime that is never started, with a scripted camera frame."""

    def __init__(self, gallery, frame=None):
        super().__init__(gallery, camera_factory=NoCamera(), speech=False, listen=False)
        self.frame_bytes = frame

    def capture(self):
        if self.frame_bytes is None:
            raise CameraUnavailable("The camera is not running.")
        return self.frame_bytes


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.gallery = Gallery(root / "faces", FakeEmbedder())
        self.runtime = FakeRuntime(self.gallery)
        static = root / "dist"
        static.mkdir()
        (static / "index.html").write_text("<html>dashboard</html>")
        self.client = create_app(self.gallery, self.runtime, None, static).test_client()

    def tearDown(self):
        self.directory.cleanup()

    def create(self, name="Priya", vector=b"1,0,0", **extra):
        data = {"name": name, "photo": (io.BytesIO(vector), "p.jpg"), **extra}
        return self.client.post("/api/people", data=data, content_type="multipart/form-data")

    def test_add_person_with_upload(self):
        response = self.create(relationship="daughter", note="Visits on Sundays.")
        self.assertEqual(response.status_code, 201, response.get_json())
        person = response.get_json()
        self.assertEqual(person["relationship"], "daughter")
        self.assertEqual(len(person["photos"]), 1)
        listed = self.client.get("/api/people").get_json()["people"]
        self.assertEqual([p["name"] for p in listed], ["Priya"])
        photo = self.client.get("/api/people/Priya/photos/" + person["photos"][0])
        self.assertEqual(photo.data, b"1,0,0")
        photo.close()

    def test_no_face_photo_leaves_no_half_saved_person(self):
        response = self.create(vector=b"none")
        self.assertEqual(response.status_code, 400)
        self.assertIn("No face", response.get_json()["error"])
        self.assertEqual(self.client.get("/api/people").get_json()["people"], [])

    def test_capture_without_camera_is_503_and_saves_nothing(self):
        response = self.client.post("/api/people", data={"name": "Priya"}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get("/api/people").get_json()["people"], [])

    def test_capture_from_camera(self):
        self.runtime.frame_bytes = b"0,1,0"
        response = self.client.post("/api/people", data={"name": "Ravi"}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.get_json()["photos"][0].startswith("capture-"))

    def test_duplicate_and_bad_names(self):
        self.create()
        self.assertEqual(self.create().status_code, 409)
        self.assertEqual(self.create(name="../x").status_code, 400)
        self.assertEqual(self.create(name="").status_code, 400)

    def test_edit_add_photo_delete_photo_delete_person(self):
        self.create()
        edited = self.client.patch("/api/people/Priya", json={"relationship": "granddaughter"}).get_json()
        self.assertEqual(edited["relationship"], "granddaughter")
        added = self.client.post(
            "/api/people/Priya/photos",
            data={"photo": (io.BytesIO(b"0.9,0.1,0"), "b.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(added.status_code, 201)
        photos = added.get_json()["photos"]
        self.assertEqual(len(photos), 2)
        self.assertEqual(self.client.delete("/api/people/Priya/photos/" + photos[0]).status_code, 204)
        self.assertEqual(self.client.delete("/api/people/Priya/photos/../../x.jpg").status_code, 404)
        self.assertEqual(self.client.delete("/api/people/Priya").status_code, 204)
        self.assertEqual(self.client.get("/api/people/Priya").status_code, 404)

    def test_wrong_file_type_is_refused(self):
        response = self.client.post(
            "/api/people",
            data={"name": "Priya", "photo": (io.BytesIO(b"x"), "p.exe")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)

    def test_status_live_events_without_camera(self):
        status = self.client.get("/api/status").get_json()
        self.assertFalse(status["camera"]["ok"])
        self.assertEqual(status["recognition"]["model"], "Facenet512")
        self.assertEqual(status["recognition"]["threshold"], 0.30)
        live = self.client.get("/api/live").get_json()
        self.assertFalse(live["camera"])
        self.assertEqual(live["faces"], [])
        self.assertEqual(self.client.get("/stream.mjpg").status_code, 503)
        self.assertEqual(self.client.get("/api/snapshot.jpg").status_code, 503)
        self.client.post("/api/speech", json={"enabled": False})
        kinds = [e["kind"] for e in self.client.get("/api/events").get_json()["events"]]
        self.assertIn("system", kinds)

    def test_location_missing_and_unknown_api(self):
        self.assertEqual(self.client.get("/api/location").status_code, 503)
        self.assertEqual(self.client.get("/api/nope").status_code, 404)

    def test_dashboard_routes_fall_back_to_index(self):
        for path in ("/", "/people/Priya", "/place"):
            response = self.client.get(path)
            self.assertIn(b"dashboard", response.data)
            response.close()


if __name__ == "__main__":
    unittest.main()
