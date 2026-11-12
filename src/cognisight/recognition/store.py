"""Transactional local profile/embedding/history storage; never stores frames."""

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from .matching import normalize


class Store:
    capacity = 100

    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.revision = 0
        self.db = sqlite3.connect(str(path), check_same_thread=False, timeout=5)
        os.chmod(path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=DELETE")
        with self.db:
            self.db.executescript(
                """
            CREATE TABLE IF NOT EXISTS people (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, relationship TEXT NOT NULL,
              note TEXT NOT NULL, pronunciation TEXT NOT NULL, active INTEGER NOT NULL,
              created REAL NOT NULL, updated REAL NOT NULL, version INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS embeddings (
              person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
              model TEXT NOT NULL, vector TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS encounters (
              id INTEGER PRIMARY KEY, person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
              started REAL NOT NULL, ended REAL);
            CREATE INDEX IF NOT EXISTS encounter_person ON encounters(person_id, started);
            PRAGMA user_version=1;
            """
            )
            # A restarted process cannot claim the person remained continuously visible.
            self.db.execute("UPDATE encounters SET ended=started WHERE ended IS NULL")

    @staticmethod
    def _fields(name, relationship, note, pronunciation):
        fields = (name, relationship, note, pronunciation)
        if any(not isinstance(x, str) for x in fields):
            raise ValueError("Profile fields must be text")
        fields = tuple(x.strip() for x in fields)
        if not fields[0] or any(len(x) > n for x, n in zip(fields, (100, 150, 500, 150))):
            raise ValueError("Name required; profile text exceeds limits")
        if any(any(ord(c) < 32 and c not in "\n\t" for c in x) for x in fields):
            raise ValueError("Invalid control characters")
        # Prevent output from containing the listening command used to interrupt speech.
        if any("cogni stop" in " ".join(x.lower().split()) for x in fields):
            raise ValueError("Profile cannot contain an activation command")
        return fields

    def enroll(self, name, relationship, note, pronunciation, vectors, model):
        fields = self._fields(name, relationship, note, pronunciation)
        vectors = [normalize(v) for v in vectors]
        if (
            len(vectors) < 10
            or len(vectors) > 50
            or len({len(v) for v in vectors}) != 1
            or not model
        ):
            raise ValueError("Enrollment requires 10–50 consistent samples and a model version")
        with self.lock, self.db:
            if self.db.execute("SELECT count(*) FROM people").fetchone()[0] >= self.capacity:
                raise ValueError("Gallery capacity reached")
            person_id = str(uuid.uuid4())
            now = time.time()
            self.db.execute(
                "INSERT INTO people VALUES(?,?,?,?,?,?, ?,?,1)", (person_id, *fields, 1, now, now)
            )
            self.db.executemany(
                "INSERT INTO embeddings VALUES(?,?,?)",
                [(person_id, model, json.dumps(v)) for v in vectors],
            )
        self.revision += 1
        return person_id

    def people(self):
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT * FROM people ORDER BY name,id")]

    def person(self, person_id):
        with self.lock:
            row = self.db.execute("SELECT * FROM people WHERE id=?", (person_id,)).fetchone()
            return dict(row) if row else None

    def update(self, person_id, name, relationship, note, pronunciation, active=True):
        fields = self._fields(name, relationship, note, pronunciation)
        with self.lock, self.db:
            cursor = self.db.execute(
                "UPDATE people SET name=?,relationship=?,note=?,pronunciation=?,active=?,updated=?,version=version+1 WHERE id=?",
                (*fields, int(bool(active)), time.time(), person_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Profile not found")
            self.revision += 1

    def add_samples(self, person_id, vectors, model):
        vectors = [normalize(v) for v in vectors]
        if not vectors:
            raise ValueError("No usable samples")
        with self.lock, self.db:
            old = self.db.execute(
                "SELECT model,vector FROM embeddings WHERE person_id=?", (person_id,)
            ).fetchall()
            if not old or any(r["model"] != model for r in old) or len(old) + len(vectors) > 50:
                raise ValueError("Profile/model mismatch or sample capacity reached")
            dim = len(json.loads(old[0]["vector"]))
            if any(len(v) != dim for v in vectors):
                raise ValueError("Embedding dimensions differ")
            self.db.executemany(
                "INSERT INTO embeddings VALUES(?,?,?)",
                [(person_id, model, json.dumps(v)) for v in vectors],
            )
            self.db.execute(
                "UPDATE people SET version=version+1,updated=? WHERE id=?", (time.time(), person_id)
            )
            self.revision += 1

    def delete(self, person_id):
        with self.lock, self.db:
            self.db.execute("DELETE FROM people WHERE id=?", (person_id,))
            self.revision += 1

    def gallery(self, model):
        with self.lock:
            rows = self.db.execute(
                "SELECT e.person_id,e.vector FROM embeddings e JOIN people p ON p.id=e.person_id WHERE p.active=1 AND e.model=?",
                (model,),
            ).fetchall()
            gallery = {}
            for row in rows:
                gallery.setdefault(row["person_id"], []).append(tuple(json.loads(row["vector"])))
            return gallery

    def start_encounter(self, person_id, utc):
        if utc is None:
            return None
        with self.lock, self.db:
            previous = self.db.execute(
                "SELECT started FROM encounters WHERE person_id=? AND ended IS NOT NULL ORDER BY started DESC LIMIT 1",
                (person_id,),
            ).fetchone()
            opened = self.db.execute(
                "SELECT id FROM encounters WHERE person_id=? AND ended IS NULL", (person_id,)
            ).fetchone()
            if not opened:
                self.db.execute(
                    "INSERT INTO encounters(person_id,started) VALUES(?,?)", (person_id, utc)
                )
            return previous[0] if previous else None

    def end_encounter(self, person_id, utc):
        with self.lock, self.db:
            self.db.execute(
                "UPDATE encounters SET ended=coalesce(?,started) WHERE person_id=? AND ended IS NULL",
                (utc, person_id),
            )

    def encounter_count(self):
        with self.lock:
            return self.db.execute("SELECT count(*) FROM encounters").fetchone()[0]

    def clear_history(self):
        with self.lock, self.db:
            self.db.execute("DELETE FROM encounters")

    def prune(self, utc):
        if utc is not None:
            with self.lock, self.db:
                self.db.execute(
                    "DELETE FROM encounters WHERE coalesce(ended,started)<?", (utc - 30 * 86400,)
                )

    def close(self):
        with self.lock:
            self.db.close()
