import os
import tempfile
import time
import unittest
from pathlib import Path

from cognisight.faces import Gallery, NoFaceError, cosine_distance, person_name, photo_filename


class FakeEmbedder:
    """Photos are text files holding a vector, or 'none' for no face.
    A frame is a list of (box, vector) pairs."""

    detector = "fake"

    def __init__(self):
        self.calls = 0

    def load(self):
        return self

    def embed(self, image):
        self.calls += 1
        if isinstance(image, list):
            return image
        text = Path(image).read_text().strip()
        if text == "none":
            return []
        return [((10, 10, 50, 50), [float(v) for v in text.split(",")])]


class GalleryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name) / "faces"
        self.embedder = FakeEmbedder()
        self.gallery = Gallery(self.root, self.embedder)

    def tearDown(self):
        self.directory.cleanup()

    def add(self, name, vector, relationship=""):
        try:
            self.gallery.get(name)
        except KeyError:
            self.gallery.create(name, relationship)
        return self.gallery.add_photo(name, vector.encode(), ".jpg")

    def test_names_cannot_escape_the_gallery(self):
        for bad in ("../Priya", "  ", ".hidden", "a/b", "a\\b", "x" * 81):
            with self.assertRaises(ValueError):
                person_name(bad)
        self.assertEqual(person_name("  Priya   Rao "), "Priya Rao")
        for bad in ("../a.jpg", "a.exe", ".x.jpg", "about.json"):
            with self.assertRaises(ValueError):
                photo_filename(bad)

    def test_person_round_trip_with_relationship_and_note(self):
        self.add("Priya", "1,0,0", relationship="daughter")
        self.gallery.update("Priya", note="Visits on Sundays.")
        person = self.gallery.get("Priya")
        self.assertEqual(person.relationship, "daughter")
        self.assertEqual(person.note, "Visits on Sundays.")
        self.assertEqual(len(person.photos), 1)

    def test_photo_without_a_face_is_rejected_and_not_kept(self):
        self.gallery.create("Priya")
        with self.assertRaises(NoFaceError):
            self.gallery.add_photo("Priya", b"none", ".jpg")
        self.assertEqual(self.gallery.get("Priya").photos, [])

    def test_best_photo_wins_and_strangers_are_unknown(self):
        self.add("Priya", "1,0,0")
        self.add("Priya", "0,1,0")
        self.add("Ravi", "0,0,1")
        faces = self.gallery.identify([((0, 0, 9, 9), [0.05, 1, 0]), ((20, 0, 9, 9), [1, 1, 1])])
        self.assertEqual(faces[0].name, "Priya")
        self.assertLess(faces[0].distance, 0.30)
        self.assertIsNone(faces[1].name)
        self.assertIsNone(faces[1].distance)

    def test_cutoff_is_030(self):
        self.add("Priya", "1,0")
        self.assertAlmostEqual(cosine_distance([1, 0], [1, 0]), 0.0)
        self.assertEqual(self.gallery.identify([((0, 0, 1, 1), [1, 0.5])])[0].name, "Priya")  # 0.106
        self.assertEqual(self.gallery.identify([((0, 0, 1, 1), [1, 1])])[0].name, "Priya")  # 0.293
        self.assertIsNone(self.gallery.identify([((0, 0, 1, 1), [0.8, 1])])[0].name)  # 0.375

    def test_empty_gallery_names_no_one(self):
        faces = self.gallery.identify([((0, 0, 1, 1), [1, 0])])
        self.assertEqual(len(faces), 1)
        self.assertIsNone(faces[0].name)

    def test_cache_survives_restart_and_rebuilds_on_change(self):
        photo = self.add("Priya", "1,0,0")
        calls = self.embedder.calls
        fresh = Gallery(self.root, self.embedder)
        fresh.refresh()
        self.assertEqual(self.embedder.calls, calls)  # loaded from cache
        photo.write_text("0,1,0")
        os.utime(photo, (time.time() + 5, time.time() + 5))
        fresh.refresh()
        self.assertEqual(self.embedder.calls, calls + 1)
        self.assertEqual(fresh.identify([((0, 0, 1, 1), [0, 1, 0])])[0].name, "Priya")

    def test_deleting_removes_from_recognition(self):
        photo = self.add("Priya", "1,0,0")
        self.gallery.delete_photo("Priya", photo.name)
        self.assertIsNone(self.gallery.identify([((0, 0, 1, 1), [1, 0, 0])])[0].name)
        self.add("Ravi", "1,0,0")
        self.gallery.delete("Ravi")
        self.assertEqual(self.gallery.people(), [self.gallery.get("Priya")])
        self.assertIsNone(self.gallery.identify([((0, 0, 1, 1), [1, 0, 0])])[0].name)

    def test_hand_copied_photo_folder_is_picked_up(self):
        folder = self.root / "Asha"
        folder.mkdir(parents=True)
        (folder / "a.jpg").write_text("1,0,0")
        self.assertEqual(self.gallery.identify([((0, 0, 1, 1), [1, 0, 0])])[0].name, "Asha")

    def test_small_box_overlapping_a_face_is_dropped_but_a_second_person_is_kept(self):
        faces = self.gallery.identify(
            [
                ((300, 310, 130, 130), [1, 0]),
                ((418, 375, 61, 61), [0, 1]),  # overlaps the first box: a pillow
                ((10, 10, 60, 60), [0, 1]),  # someone else in the room
            ]
        )
        self.assertEqual([f.box for f in faces], [(300, 310, 130, 130), (10, 10, 60, 60)])

    def test_duplicate_person_is_refused(self):
        self.gallery.create("Priya")
        with self.assertRaises(FileExistsError):
            self.gallery.create("  Priya ")


if __name__ == "__main__":
    unittest.main()
