"""Talking signposts: printed markers beside doors, and directions between them.

Each sign is an ArUco marker (dictionary 4x4_50) with a room name. When the
camera reads one, the wearer is facing it, so directions written "for someone
standing in front of this sign" are always the right way round. A caregiver
links signs with one sentence each, and a trip to a room is spoken one step per
sign until the destination's own sign is seen.

Everything is stored in one JSON file next to the face gallery.
"""

from collections import deque
import json
import math
import os
from pathlib import Path
import re
import threading
import time

MARKER_COUNT = 50
MIN_MARKER_SIDE = 24  # pixels at 640x480. A 14 cm sign is about 74/d px wide at d metres
# on the Pi Camera Module 2 (62.2° wide), so 24 px is about 3 m. In practice the
# detector itself stops decoding below about 30 px, so signs read to about 2.5 m.
RECENT_SECONDS = 120  # a sign seen this recently tells us where they are
ARRIVAL_COOLDOWN = 120  # "This is the kitchen." at most this often per sign
STEP_REPEAT = 30  # repeat a guidance step if they linger in front of a sign
ARRIVED_SHOWN = 20  # a finished trip stays on the dashboard this long

PLAN_LIMITS = {"walls": 400, "doors": 100, "labels": 60}
DEFAULT_PLAN = {"width": 12.0, "height": 9.0, "walls": [], "doors": [], "labels": [], "signs": []}


def sign_name(name):
    if not isinstance(name, str):
        raise ValueError("A sign needs a name.")
    cleaned = " ".join(name.split())
    if not cleaned or len(cleaned) > 40:
        raise ValueError("Give the sign a name of up to 40 characters, such as Kitchen.")
    return cleaned


def the(name):
    """'the kitchen' for 'Kitchen'; "Priya's room", 'my room' and 'TV room'
    keep their own words and capitals. The dashboard words it the same way."""
    lowered = name.lower()
    if lowered.startswith("the "):
        return "the " + name[4:]
    if re.match(r"^\S+['’]s(\s|$)", name) or lowered.startswith(("my ", "your ")):
        return name
    if re.match(r"^[A-Z][a-z]", name):
        name = name[0].lower() + name[1:]
    return "the " + name


def _clean_aliases(aliases):
    if isinstance(aliases, str):
        aliases = aliases.split(",")
    if not isinstance(aliases, (list, tuple)):
        return []
    cleaned = []
    for alias in aliases:
        alias = " ".join(str(alias).split())[:40]
        if alias and alias.lower() not in (a.lower() for a in cleaned):
            cleaned.append(alias)
    return cleaned[:10]


def _number(value, low, high, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return round(min(max(number, low), high), 3)


class SignStore:
    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._data = self._load()

    # ------------------------------------------------------------ signs

    def signs(self):
        with self._lock:
            return [dict(sign) for sign in sorted(self._data["signs"], key=lambda s: s["name"].lower())]

    def get(self, sign_id):
        with self._lock:
            for sign in self._data["signs"]:
                if sign["id"] == sign_id:
                    return dict(sign)
        return None

    def create(self, name, aliases=None, note="", say_note=False):
        name = sign_name(name)
        with self._lock:
            self._check_name_free(name)
            used = {sign["id"] for sign in self._data["signs"]}
            free = [number for number in range(MARKER_COUNT) if number not in used]
            if not free:
                raise OverflowError("All {} printable signs are in use. Delete one first.".format(MARKER_COUNT))
            sign = {
                "id": free[0],
                "name": name,
                "aliases": _clean_aliases(aliases or []),
                "note": str(note or "").strip()[:300],
                "say_note": bool(say_note),
            }
            self._data["signs"].append(sign)
            self._save()
            return dict(sign)

    def update(self, sign_id, **fields):
        with self._lock:
            sign = self._find(sign_id)
            if "name" in fields and fields["name"] is not None:
                name = sign_name(fields["name"])
                self._check_name_free(name, ignore=sign_id)
                sign["name"] = name
            if "aliases" in fields and fields["aliases"] is not None:
                sign["aliases"] = _clean_aliases(fields["aliases"])
            if "note" in fields and fields["note"] is not None:
                sign["note"] = str(fields["note"]).strip()[:300]
            if "say_note" in fields and fields["say_note"] is not None:
                sign["say_note"] = bool(fields["say_note"])
            self._save()
            return dict(sign)

    def delete(self, sign_id):
        with self._lock:
            sign = self._find(sign_id)
            self._data["signs"].remove(sign)
            self._data["links"] = [
                link for link in self._data["links"] if sign_id not in (link["from"], link["to"])
            ]
            self._data["plan"]["signs"] = [p for p in self._data["plan"]["signs"] if p["sign"] != sign_id]
            self._save()

    def find_destination(self, text):
        """The sign whose name or other name appears in a spoken phrase."""
        spoken = " " + re.sub(r"[^a-z0-9' ]", " ", (text or "").lower().replace("’", "'")) + " "
        spoken = " ".join(spoken.split())
        best, best_length = None, 0
        for sign in self.signs():
            for name in [sign["name"]] + sign["aliases"]:
                term = " ".join(re.sub(r"[^a-z0-9' ]", " ", name.lower()).split())
                if term and re.search(r"(^| )" + re.escape(term) + r"( |$)", spoken) and len(term) > best_length:
                    best, best_length = sign, len(term)
        return best

    # ------------------------------------------------------------ links

    def links(self):
        with self._lock:
            return [dict(link) for link in self._data["links"]]

    def set_links(self, sign_id, links):
        with self._lock:
            self._find(sign_id)
            known = {sign["id"] for sign in self._data["signs"]}
            kept = [link for link in self._data["links"] if link["from"] != sign_id]
            seen = set()
            for link in links or []:
                if not isinstance(link, dict):
                    raise ValueError("Each direction needs a sign and a sentence.")
                try:
                    to = int(link.get("to"))
                except (TypeError, ValueError):
                    raise ValueError("Choose which sign this direction leads to.")
                text = " ".join(str(link.get("text") or "").split())[:240]
                if to not in known or to == sign_id:
                    raise ValueError("A direction must lead to another sign.")
                if not text:
                    raise ValueError("Write the direction as one sentence, such as “Turn left.”")
                if to in seen:
                    raise ValueError("There are two directions to the same sign.")
                seen.add(to)
                kept.append({"from": sign_id, "to": to, "text": text})
            self._data["links"] = kept
            self._save()
            return self.links()

    def link_text(self, a, b):
        for link in self.links():
            if link["from"] == a and link["to"] == b:
                return link["text"]
        return None

    def route(self, start, goal):
        """Fewest signs from start to goal, following written directions."""
        if start == goal:
            return [start]
        neighbours = {}
        for link in self.links():
            neighbours.setdefault(link["from"], []).append(link["to"])
        previous = {start: None}
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for nxt in neighbours.get(current, []):
                if nxt in previous:
                    continue
                previous[nxt] = current
                if nxt == goal:
                    path = [goal]
                    while previous[path[-1]] is not None:
                        path.append(previous[path[-1]])
                    return list(reversed(path))
                queue.append(nxt)
        return None

    # ------------------------------------------------------------ plan

    def plan(self):
        with self._lock:
            return json.loads(json.dumps(self._data["plan"]))

    def set_plan(self, plan):
        if not isinstance(plan, dict):
            raise ValueError("That is not a floor plan.")
        width = _number(plan.get("width"), 2, 50, DEFAULT_PLAN["width"])
        height = _number(plan.get("height"), 2, 50, DEFAULT_PLAN["height"])

        def items(key):
            value = plan.get(key, [])
            if not isinstance(value, list):
                raise ValueError("The plan's {} must be a list.".format(key))
            if len(value) > PLAN_LIMITS.get(key, MARKER_COUNT):
                raise ValueError("A plan can hold at most {} {}.".format(PLAN_LIMITS.get(key, MARKER_COUNT), key))
            return [item for item in value if isinstance(item, dict)]

        x = lambda v: _number(v, 0, width)
        y = lambda v: _number(v, 0, height)
        angle = lambda v: round(_number(v, -1e6, 1e6) % 360, 3)
        with self._lock:
            known = {sign["id"] for sign in self._data["signs"]}
            placed = {}
            for item in items("signs"):
                try:
                    sign = int(item.get("sign"))
                except (TypeError, ValueError):
                    continue
                if sign in known:
                    placed[sign] = {"sign": sign, "x": x(item.get("x")), "y": y(item.get("y")), "facing": angle(item.get("facing"))}
            cleaned = {
                "width": width,
                "height": height,
                "walls": [
                    {"x1": x(w.get("x1")), "y1": y(w.get("y1")), "x2": x(w.get("x2")), "y2": y(w.get("y2"))}
                    for w in items("walls")
                ],
                "doors": [
                    {"x": x(d.get("x")), "y": y(d.get("y")), "angle": angle(d.get("angle")),
                     "width": _number(d.get("width"), 0.5, 3, 0.9)}
                    for d in items("doors")
                ],
                "labels": [
                    {"x": x(l.get("x")), "y": y(l.get("y")), "text": " ".join(str(l.get("text") or "").split())[:40]}
                    for l in items("labels")
                    if str(l.get("text") or "").strip()
                ],
                "signs": list(placed.values()),
            }
            self._data["plan"] = cleaned
            self._save()
            return self.plan()

    # ------------------------------------------------------------ storage

    def _find(self, sign_id):
        for sign in self._data["signs"]:
            if sign["id"] == sign_id:
                return sign
        raise KeyError(sign_id)

    def _check_name_free(self, name, ignore=None):
        for sign in self._data["signs"]:
            if sign["id"] != ignore and sign["name"].lower() == name.lower():
                raise FileExistsError("There is already a sign called {}.".format(sign["name"]))

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        plan = data.get("plan") if isinstance(data.get("plan"), dict) else {}
        merged = dict(DEFAULT_PLAN)
        merged.update({k: v for k, v in plan.items() if k in DEFAULT_PLAN})
        return {
            "signs": [s for s in data.get("signs", []) if isinstance(s, dict) and "id" in s and "name" in s],
            "links": [l for l in data.get("links", []) if isinstance(l, dict) and {"from", "to", "text"} <= set(l)],
            "plan": merged,
        }

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        os.replace(temp, self.path)


class Navigator:
    """Where the wearer is (the last sign seen) and the trip in progress.

    ``say(text)`` speaks to the wearer; ``event(kind, name, text)`` adds to the
    dashboard timeline.
    """

    def __init__(self, store, say, event=lambda *args: None, clock=time.time, can_speak=lambda: True):
        self.store = store
        self._say = say
        self._can_speak = can_speak
        self._event = event
        self._clock = clock
        self._lock = threading.RLock()
        self.room = None
        self.guide = None
        self.last_seen = {}
        self._last_arrival = {}
        self._last_step = 0.0

    # ------------------------------------------------------------ sightings

    def seen(self, sign_ids):
        for sign_id in sign_ids:
            self.sighting(sign_id)

    def sighting(self, sign_id):
        sign = self.store.get(sign_id)
        if sign is None:
            return
        with self._lock:
            now = self._clock()
            previous_sighting = self.last_seen.get(sign_id, -math.inf)
            self.last_seen[sign_id] = now
            if self.room is None or self.room["id"] != sign_id:
                self.room = {"id": sign_id, "name": sign["name"], "since": now, "seen_at": now}
                self._event("room", sign["name"], "In {}".format(the(sign["name"])))
            else:
                self.room["seen_at"] = now
                self.room["name"] = sign["name"]
            if self.guide is not None and not self.guide.get("arrived"):
                self._guide_step(sign, now)
                return
            # Name the room when they arrive, not every few minutes while they
            # stay in front of the sign, and not before speech can be heard.
            away = now - previous_sighting >= ARRIVAL_COOLDOWN or self._last_arrival.get(sign_id) is None
            if away and now - self._last_arrival.get(sign_id, -math.inf) >= ARRIVAL_COOLDOWN and self._can_speak():
                self._last_arrival[sign_id] = now
                text = "This is {}.".format(the(sign["name"]))
                if sign.get("say_note") and sign.get("note"):
                    text += " " + sign["note"]
                self._say(text)

    def _guide_step(self, sign, now):
        guide = self.guide
        sign_id = sign["id"]
        destination = guide["destination"]
        if sign_id == destination["id"]:
            text = "You're at {}.".format(the(destination["name"]))
            self._say(text)
            self._event("guide", destination["name"], "Arrived at {}".format(the(destination["name"])))
            self._last_arrival[sign_id] = now
            if sign_id not in guide["visited"]:
                guide["visited"].append(sign_id)
            if destination["id"] not in guide["route"]:
                guide["route"] = guide["visited"][:]
            guide["at"] = sign_id
            guide["said"] = text
            guide["arrived"] = now  # kept briefly so the dashboard can show it
            return
        if guide["at"] == sign_id and now - self._last_step < STEP_REPEAT:
            return
        # A sign passed on a trip has had its say; don't name it again on the way back.
        self._last_arrival[sign_id] = now
        path = self.store.route(sign_id, destination["id"])
        if sign_id in guide["visited"]:
            # Back at a sign already passed: forget the detour after it.
            guide["visited"] = guide["visited"][: guide["visited"].index(sign_id) + 1]
        else:
            guide["visited"].append(sign_id)
        guide["at"] = sign_id
        self._last_step = now
        if not path:
            text = "I don't know the way to {} from here.".format(the(destination["name"]))
            guide["said"] = text
            self._say(text)
            self._event("guide", destination["name"], "No directions from {} to {}".format(the(sign["name"]), the(destination["name"])))
            return
        text = self.store.link_text(sign_id, path[1])
        guide["route"] = guide["visited"][:-1] + path
        guide["said"] = text
        self._say(text)
        self._event("guide", destination["name"], "At {}: “{}”".format(the(sign["name"]), text))

    # ------------------------------------------------------------ trips

    def start(self, destination_id):
        destination = self.store.get(destination_id)
        if destination is None:
            raise KeyError(destination_id)
        with self._lock:
            now = self._clock()
            self.guide = {
                "destination": {"id": destination["id"], "name": destination["name"]},
                "route": [],
                "visited": [],
                "at": None,
                "said": None,
                "started": now,
            }
            self._event("guide", destination["name"], "Guiding to {}".format(the(destination["name"])))
            here = self.room if self.room and now - self.room["seen_at"] <= RECENT_SECONDS else None
            if here is None:
                text = "Let's go to {}. Look around for a sign on the wall.".format(the(destination["name"]))
                self.guide["said"] = text
                self._say(text)
            else:
                self._last_step = 0.0
                sign = self.store.get(here["id"])
                if sign is not None:
                    self._guide_step(sign, now)
            return self.state()["guide"]

    def stop(self, reason="Stopped guiding"):
        with self._lock:
            if self.guide is not None:
                self._event("guide", self.guide["destination"]["name"], reason)
            self.guide = None

    def forget(self, sign_id):
        """A sign was deleted."""
        with self._lock:
            self.last_seen.pop(sign_id, None)
            if self.room and self.room["id"] == sign_id:
                self.room = None
            if self.guide and self.guide["destination"]["id"] == sign_id:
                self.guide = None

    def state(self):
        with self._lock:
            if self.guide and self.guide.get("arrived") and self._clock() - self.guide["arrived"] > ARRIVED_SHOWN:
                self.guide = None
            guide = None
            if self.guide is not None:
                guide = {key: value for key, value in self.guide.items() if key != "visited"}
                guide["route"] = list(guide["route"])
            return {"room": dict(self.room) if self.room else None, "guide": guide}


# ---------------------------------------------------------------- detection


class MarkerDetector:
    """Finds sign markers in a BGR frame with OpenCV's ArUco module."""

    def __init__(self, min_side=MIN_MARKER_SIDE):
        import cv2

        self._cv2 = cv2
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        self._detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
        self.min_side = min_side

    def detect(self, frame):
        """[(id, [[x, y] * 4])] for markers close enough to act on."""
        gray = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        corners, ids, _ = self._detector.detectMarkers(gray)
        if ids is None:
            return []
        found = []
        for marker_corners, marker_id in zip(corners, ids.ravel()):
            points = [[float(x), float(y)] for x, y in marker_corners.reshape(4, 2)]
            if _shortest_side(points) >= self.min_side:
                found.append((int(marker_id), points))
        return found


def _shortest_side(points):
    return min(
        math.dist(points[i], points[(i + 1) % 4]) for i in range(4)
    )
