"""Conservative spatial tracking with consecutive confirmation and expiry."""

from dataclasses import dataclass
from typing import Optional


def iou(a, b):
    x = max(a[0], b[0])
    y = max(a[1], b[1])
    w = max(0, min(a[0] + a[2], b[0] + b[2]) - x)
    h = max(0, min(a[1] + a[3], b[1] + b[3]) - y)
    overlap = w * h
    return overlap / max(1, a[2] * a[3] + b[2] * b[3] - overlap)


@dataclass
class Track:
    id: int
    bbox: tuple
    last_seen: float
    candidate: Optional[str] = None
    streak: int = 0
    person_id: Optional[str] = None
    confirmed_at: Optional[float] = None


@dataclass(frozen=True)
class TrackEvent:
    kind: str
    track_id: int
    person_id: str


class Tracker:
    def __init__(self):
        self.tracks = {}
        self.last_update = None
        self.next_id = 1
        self.announced = {}

    def update(self, detections, now):
        self.last_update = now
        events = []
        unused = set(self.tracks)
        for bbox, match in detections[:4]:
            candidates = sorted(
                ((iou(bbox, self.tracks[key].bbox), key) for key in unused), reverse=True
            )
            # If overlap is ambiguous, create a fresh unconfirmed track instead of swapping identities.
            if (
                candidates
                and candidates[0][0] >= 0.3
                and (len(candidates) == 1 or candidates[0][0] - candidates[1][0] >= 0.1)
            ):
                key = candidates[0][1]
                unused.remove(key)
                track = self.tracks[key]
            else:
                track = Track(self.next_id, bbox, now)
                self.tracks[track.id] = track
                self.next_id += 1
            track.bbox, track.last_seen = bbox, now
            candidate = match.person_id if match.state == "known" else None
            if candidate != track.person_id and track.person_id:
                events.append(TrackEvent("lost", track.id, track.person_id))
                track.person_id = None
                track.confirmed_at = None
            track.streak = (
                track.streak + 1
                if candidate and candidate == track.candidate
                else int(bool(candidate))
            )
            track.candidate = candidate
            if track.streak >= 3 and not track.person_id:
                track.person_id = candidate
                track.confirmed_at = now
                events.append(TrackEvent("confirmed", track.id, candidate))
        for key in unused:
            track = self.tracks[key]
            track.streak = 0
            track.candidate = None
            if now - track.last_seen >= 10:
                if track.person_id:
                    events.append(TrackEvent("lost", key, track.person_id))
                del self.tracks[key]
        return events

    def visible(self, now):
        return [
            t
            for t in self.tracks.values()
            if t.person_id
            and t.candidate == t.person_id
            and t.streak >= 3
            and now - t.last_seen <= 1
        ]

    def recent(self, person_id, now):
        return any(
            t.person_id == person_id and now - t.last_seen <= 10 for t in self.tracks.values()
        )

    def should_announce(self, person_id, now):
        if now - self.announced.get(person_id, float("-inf")) < 60:
            return False
        self.announced[person_id] = now
        return True

    def primary(self, now, width, height):
        def score(t):
            x, y, w, h = t.bbox
            distance = abs((x + w / 2) / width - 0.5) + abs((y + h / 2) / height - 0.5)
            return w * h / (1 + distance)

        # Select a face before selecting its identity. Unknown foreground faces
        # must not redirect requests to known people in the background.
        current = [
            t
            for t in self.tracks.values()
            if t.last_seen == self.last_update and now - t.last_seen <= 1
        ]
        choices = sorted(current, key=score, reverse=True)
        if not choices or (len(choices) > 1 and score(choices[1]) >= score(choices[0]) * 0.85):
            return None
        return choices[0] if choices[0] in self.visible(now) else None
