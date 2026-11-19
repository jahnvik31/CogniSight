"""People the device knows, and who is in a camera frame.

Each person is a folder of photos under the gallery root, with an optional
``about.json`` holding their relationship and a note. The photos are the
record. Embeddings are a cache built from them and rebuilt when a photo
changes.

Recognition follows VISU-X with one correction: Facenet512, the OpenCV face
detector, cosine distance, and a 0.30 cutoff (VISU-X's 0.70 named strangers).
A person's score is their best (smallest) distance over all of their photos,
so more photos from different angles make the match steadier.
"""

from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import threading
import time
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
DEEPFACE_HOME = REPO_ROOT / ".models" / "deepface"

MODEL = "Facenet512"
DETECTOR = "opencv"
THRESHOLD = 0.30
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp"}
ABOUT_FILE = "about.json"
CACHE_FILE = ".cognisight-embeddings.json"


class NoFaceError(ValueError):
    """The photo has no face the detector could find."""


@dataclass(frozen=True)
class Face:
    box: Tuple[int, int, int, int]
    name: Optional[str] = None
    distance: Optional[float] = None


@dataclass
class Person:
    name: str
    relationship: str = ""
    note: str = ""
    photos: List[str] = field(default_factory=list)


def person_name(name):
    if not isinstance(name, str):
        raise ValueError("A person's name must be text.")
    cleaned = " ".join(name.split())
    if not cleaned or cleaned in (".", "..") or len(cleaned) > 80:
        raise ValueError("Enter a name of up to 80 characters.")
    if cleaned.startswith("."):
        raise ValueError("A name cannot start with a dot.")
    if any(bad in cleaned for bad in ("/", "\\", "\x00", ":")):
        raise ValueError("A name cannot contain / \\ or :")
    return cleaned


def photo_filename(filename):
    """A safe file name inside a person's folder, or ValueError."""
    if not isinstance(filename, str) or not filename:
        raise ValueError("Missing photo name.")
    name = Path(filename).name
    if name != filename or name.startswith(".") or Path(name).suffix.lower() not in PHOTO_TYPES:
        raise ValueError("That is not a photo in this gallery.")
    return name


def cosine_distance(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if norm == 0:
        return 1.0
    return 1.0 - dot / norm


class Gallery:
    """Folder-backed people store with an embedding cache.

    ``embedder.embed(image)`` takes a file path or a BGR array and returns a
    list of ``(box, vector)`` pairs, one per detected face.
    """

    def __init__(self, root, embedder=None, threshold=THRESHOLD):
        self.root = Path(root)
        self.threshold = threshold
        self._embedder = embedder
        self._lock = threading.RLock()
        self._cache = None  # relative path -> {"stamp": [...], "vector": [...] | None}

    # ------------------------------------------------------------ embedder

    @property
    def embedder(self):
        if self._embedder is None:
            self._embedder = DeepFaceEmbedder()
        return self._embedder

    # ------------------------------------------------------------ people

    def people(self):
        with self._lock:
            if not self.root.is_dir():
                return []
            found = []
            for folder in sorted(self.root.iterdir(), key=lambda p: p.name.lower()):
                if not folder.is_dir() or folder.name.startswith("."):
                    continue
                found.append(self._read_person(folder))
            return found

    def get(self, name):
        folder = self._folder(name)
        with self._lock:
            if not folder.is_dir():
                raise KeyError(name)
            return self._read_person(folder)

    def create(self, name, relationship="", note=""):
        cleaned = person_name(name)
        folder = self.root / cleaned
        with self._lock:
            if folder.exists():
                raise FileExistsError("{} is already saved.".format(cleaned))
            folder.mkdir(parents=True)
            self._write_about(folder, relationship, note)
            return self._read_person(folder)

    def update(self, name, relationship=None, note=None):
        folder = self._existing(name)
        with self._lock:
            current = self._read_about(folder)
            self._write_about(
                folder,
                current["relationship"] if relationship is None else relationship,
                current["note"] if note is None else note,
            )
            return self._read_person(folder)

    def delete(self, name):
        folder = self._existing(name)
        with self._lock:
            for path in folder.iterdir():
                if path.is_file():
                    path.unlink()
            folder.rmdir()
            self._forget(folder.name)

    def add_photo(self, name, data, suffix=".jpg", stem="photo"):
        """Save photo bytes for a person. Raises NoFaceError and keeps nothing
        when the detector finds no face in it."""
        folder = self._existing(name)
        suffix = suffix.lower() if suffix and suffix.lower() in PHOTO_TYPES else ".jpg"
        with self._lock:
            target = _unique(folder / "{}-{}{}".format(stem, int(time.time()), suffix))
            target.write_bytes(data)
            try:
                vector = self._embed_photo(target)
            except Exception:
                target.unlink()
                raise
            if vector is None:
                target.unlink()
                raise NoFaceError(
                    "No face was found in that photo. Use a clear, well-lit photo facing the camera."
                )
            return target

    def delete_photo(self, name, filename):
        folder = self._existing(name)
        path = folder / photo_filename(filename)
        with self._lock:
            if not path.is_file():
                raise KeyError(filename)
            path.unlink()
            self._load_cache().pop(self._key(path), None)
            self._save_cache()

    def photo_path(self, name, filename):
        folder = self._existing(name)
        path = folder / photo_filename(filename)
        if not path.is_file():
            raise KeyError(filename)
        return path

    # ------------------------------------------------------------ recognition

    def refresh(self):
        """Embed new or changed photos and drop removed ones. Returns the
        number of usable photos."""
        with self._lock:
            cache = self._load_cache()
            seen = set()
            changed = False
            for person in self.people():
                for filename in person.photos:
                    path = self.root / person.name / filename
                    key = self._key(path)
                    seen.add(key)
                    entry = cache.get(key)
                    if entry is None or entry.get("stamp") != _stamp(path):
                        self._embed_photo(path, save=False)
                        changed = True
            for key in [key for key in cache if key not in seen]:
                del cache[key]
                changed = True
            if changed:
                self._save_cache()
            return sum(1 for entry in cache.values() if entry.get("vector"))

    def known_vectors(self):
        """[(name, vector)] for every photo with a face."""
        with self._lock:
            self.refresh()
            pairs = []
            for key, entry in self._load_cache().items():
                if entry.get("vector"):
                    pairs.append((key.split("/", 1)[0], entry["vector"]))
            return pairs

    def match(self, vector, known):
        """Best person for one face vector, or (None, None)."""
        best = {}
        for name, candidate in known:
            distance = cosine_distance(vector, candidate)
            if distance < best.get(name, math.inf):
                best[name] = distance
        if not best:
            return None, None
        name = min(best, key=best.get)
        distance = best[name]
        if distance > self.threshold:
            return None, None
        return name, round(distance, 4)

    def identify(self, image, known=None):
        """Every face in an image (path or BGR array), named when known."""
        if known is None:
            known = self.known_vectors()
        faces = []
        for box, vector in drop_nested(self.embedder.embed(image)):
            name, distance = self.match(vector, known)
            faces.append(Face(box=tuple(int(v) for v in box), name=name, distance=distance))
        return faces

    # ------------------------------------------------------------ internals

    def _folder(self, name):
        return self.root / person_name(name)

    def _existing(self, name):
        folder = self._folder(name)
        if not folder.is_dir():
            raise KeyError(name)
        return folder

    def _read_person(self, folder):
        about = self._read_about(folder)
        photos = sorted(
            path.name
            for path in folder.iterdir()
            if path.is_file() and not path.name.startswith(".") and path.suffix.lower() in PHOTO_TYPES
        )
        return Person(folder.name, about["relationship"], about["note"], photos)

    @staticmethod
    def _read_about(folder):
        try:
            data = json.loads((folder / ABOUT_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        return {
            "relationship": str(data.get("relationship") or "")[:80],
            "note": str(data.get("note") or "")[:500],
        }

    @staticmethod
    def _write_about(folder, relationship, note):
        payload = {
            "relationship": " ".join(str(relationship or "").split())[:80],
            "note": str(note or "").strip()[:500],
        }
        (folder / ABOUT_FILE).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _key(self, path):
        return "{}/{}".format(path.parent.name, path.name)

    def _embed_photo(self, path, save=True):
        faces = self.embedder.embed(str(path))
        vector = None
        if faces:
            # The largest face in a portrait is the person it is of.
            box, vector = max(faces, key=lambda item: item[0][2] * item[0][3])
            vector = [float(v) for v in vector]
        self._load_cache()[self._key(path)] = {"stamp": _stamp(path), "vector": vector}
        if save:
            self._save_cache()
        return vector

    def _forget(self, name):
        cache = self._load_cache()
        for key in [key for key in cache if key.split("/", 1)[0] == name]:
            del cache[key]
        self._save_cache()

    def _load_cache(self):
        if self._cache is None:
            try:
                data = json.loads((self.root / CACHE_FILE).read_text(encoding="utf-8"))
                self._cache = data if isinstance(data, dict) else {}
            except (OSError, ValueError):
                self._cache = {}
        return self._cache

    def _save_cache(self):
        if not self.root.is_dir():
            return
        temp = self.root / (CACHE_FILE + ".tmp")
        temp.write_text(json.dumps(self._cache), encoding="utf-8")
        os.replace(temp, self.root / CACHE_FILE)


class DeepFaceEmbedder:
    """DeepFace Facenet512. Imported lazily so tests and the page work without it."""

    def __init__(self, detector=DETECTOR):
        self.detector = detector
        self._deepface = None
        # TensorFlow models are not safe to call from two threads at once.
        self._lock = threading.Lock()

    def load(self):
        with self._lock:
            return self._load()

    def _load(self):
        if self._deepface is None:
            DEEPFACE_HOME.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("DEEPFACE_HOME", str(DEEPFACE_HOME))
            os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
            try:
                from deepface import DeepFace
            except ImportError as exc:
                raise RuntimeError(
                    "Face recognition is not installed. Run ./setup.sh again."
                ) from exc
            DeepFace.build_model(MODEL)
            self._deepface = DeepFace
        return self._deepface

    def embed(self, image):
        deepface = self.load()
        try:
            with self._lock:
                rows = deepface.represent(
                    img_path=image,
                    model_name=MODEL,
                    detector_backend=self.detector,
                    enforce_detection=False,
                    align=True,
                    normalization="base",
                )
        except ValueError:
            return []
        faces = []
        for row in rows:
            area = row.get("facial_area") or {}
            box = (area.get("x", 0), area.get("y", 0), area.get("w", 0), area.get("h", 0))
            # With enforce_detection off, "no face" comes back as the whole
            # image with zero confidence.
            if not row.get("face_confidence") and box[0] == 0 and box[1] == 0:
                continue
            if box[2] <= 0 or box[3] <= 0:
                continue
            faces.append((box, row["embedding"]))
        return faces


def drop_nested(faces, limit=0.15):
    """Drop detections that overlap a larger face. The OpenCV detector
    sometimes adds a small box on a pillow or collar beside a real face."""
    ordered = sorted(faces, key=lambda item: item[0][2] * item[0][3], reverse=True)
    kept = []
    for box, vector in ordered:
        area = max(box[2] * box[3], 1)
        if all(_overlap(box, other) / area <= limit for other, _ in kept):
            kept.append((box, vector))
    return kept


def _overlap(a, b):
    width = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    height = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(width, 0) * max(height, 0)


def _stamp(path):
    stat = path.stat()
    return [stat.st_mtime_ns, stat.st_size]


def _unique(path):
    if not path.exists():
        return path
    for number in range(2, 1000):
        candidate = path.with_name("{}-{}{}".format(path.stem, number, path.suffix))
        if not candidate.exists():
            return candidate
    raise FileExistsError("Too many photos named {}".format(path.name))
