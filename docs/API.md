# CogniSight device API

The Pi serves this API, the built dashboard, and the camera stream on port 8765.
All times are Unix epoch seconds (float). Errors are `{"error": "plain sentence"}`
with a 4xx or 5xx status.

## Live

`GET /stream.mjpg` — MJPEG stream (`multipart/x-mixed-replace`) of the camera with
boxes and names drawn on it. 503 when no camera is running.

`GET /api/snapshot.jpg` — one JPEG frame with boxes drawn. 503 when no camera.

`GET /api/live`

```json
{
  "camera": true,
  "frame": {"width": 640, "height": 480},
  "faces": [{"name": "Priya", "relationship": "daughter", "distance": 0.21, "box": [120, 80, 140, 140]},
            {"name": null, "relationship": null, "distance": null, "box": [300, 90, 120, 120]}],
  "updated": 1763540000.5,
  "said": {"text": "This is Priya, your daughter.", "at": 1763539990.2}
}
```

`faces` is the latest recognition pass (empty when nobody is in frame). `said` is
the last sentence spoken to the wearer, or null.

`GET /api/events?limit=50` — newest first.

```json
{"events": [{"id": 12, "kind": "seen", "name": "Priya", "text": "Priya is in view", "at": 1763540000.1}]}
```

`kind` is one of `seen` (a known person came into view), `unknown` (a face the
device does not know), `said` (speech to the wearer), `heard` (a voice command
the device understood), `system` (camera started, speech failed, and so on).

## Device

`GET /api/status`

```json
{
  "hostname": "cognisight",
  "urls": ["http://cognisight.local:8765", "http://192.168.1.20:8765"],
  "uptime": 512.0,
  "camera": {"ok": true, "label": "imx219", "kind": "picamera2", "error": null},
  "recognition": {"ok": true, "model": "Facenet512", "detector": "opencv", "threshold": 0.3,
                  "seconds_per_check": 0.8, "error": null},
  "speech": {"available": true, "enabled": true, "error": null},
  "listening": {"available": false, "enabled": false, "error": "No microphone found", "heard": null},
  "people": 3,
  "signs": {"ok": true, "count": 4, "error": null}
}
```

`POST /api/speech` JSON `{"enabled": true|false}` → the `speech` object.
`POST /api/speech/test` JSON `{"text": "optional"}` → `{"ok": true}`; speaks a test sentence.
`POST /api/listening` JSON `{"enabled": true|false}` → the `listening` object.

## People

A person:

```json
{"name": "Priya", "relationship": "daughter", "note": "Visits on Sundays.",
 "photos": ["a.jpg", "capture-1763540000.jpg"], "last_seen": 1763540000.1}
```

`GET /api/people` → `{"people": [person, ...]}` sorted by name.

`POST /api/people` multipart: `name` (required), `relationship`, `note`,
`photo` (file, optional). With no photo, the device captures one from the camera.
→ 201 person. 400 bad name or no face; 409 name already exists; 503 no camera when
capturing.

`PATCH /api/people/<name>` JSON `{"relationship": "...", "note": "..."}` → person.

`DELETE /api/people/<name>` → 204.

`POST /api/people/<name>/photos` multipart `photo` (file, optional; captures from
the camera when absent) → 201 person.

`GET /api/people/<name>/photos/<filename>` → the image.

`DELETE /api/people/<name>/photos/<filename>` → 204.

## Location

`GET /api/location` → the last result (looked up on first call, cached 5 minutes).
`POST /api/location/refresh` → a fresh lookup.

```json
{"status": "ok", "source": "wifi", "lat": 16.4955, "lng": 80.5098, "accuracy": 40.0,
 "access_points": 6, "checked_at": 1763540000.0, "error": null}
```

`status` is `ok`, `not_configured` (no `GEOLOCATION_API_KEY` on the Pi), or `error`.
`source` is `wifi` when at least two Wi-Fi access points were sent, otherwise `ip`
(Google placed the device from its internet address, usually kilometres off).
`accuracy` is the radius in metres.

## Home: signs, directions, and the floor plan

Signs are printed ArUco markers (dictionary 4x4_50, ids 0–49) placed beside
doors. The device recognises a sign when the camera sees its marker large
enough (about 2.5 m or closer for a sign printed at 14 cm). Stored in `data/signs.json`.

A sign:

```json
{"id": 3, "name": "Hallway", "aliases": ["corridor"], "note": "Your room is the blue door.",
 "say_note": true, "last_seen": 1763540000.1}
```

`id` is also the marker number; the device picks the lowest free one.
`aliases` are other names the wearer might say ("toilet", "washroom").
`say_note` decides whether the note is spoken after "This is the hallway.".

A link is one step of directions, written for someone standing in front of
the `from` sign:

```json
{"from": 3, "to": 5, "text": "The bathroom is the second door on your right."}
```

The floor plan, in metres, origin top-left, y pointing down. Angles are degrees,
0 pointing right (east on the drawing), 90 pointing down:

```json
{"width": 12, "height": 9,
 "walls": [{"x1": 0, "y1": 0, "x2": 12, "y2": 0}],
 "doors": [{"x": 3, "y": 0, "angle": 0, "width": 0.9}],
 "labels": [{"x": 2, "y": 2, "text": "Kitchen"}],
 "signs": [{"sign": 3, "x": 4.5, "y": 0.1, "facing": 90}]}
```

`doors.angle` is the direction of the wall the door sits in. `signs.facing` is
the direction the printed side faces, which is where someone must stand to read
it. Limits: width and height 2–50, 400 walls, 100 doors, 60 labels.

`GET /api/home`

```json
{"signs": [sign, ...], "links": [link, ...], "plan": plan,
 "room": {"id": 3, "name": "Hallway", "since": 1763539000.0, "seen_at": 1763540000.1} ,
 "guide": {"destination": {"id": 5, "name": "Bathroom"}, "route": [1, 3, 5],
           "at": 3, "said": "The bathroom is the second door on your right.", "started": 1763539990.0,
           "arrived": null}}
```

`room` is where the wearer was last seen (the last sign the camera read), or
null. When the destination's sign is reached, `arrived` is set to that time
and `at` to the destination; the finished trip stays visible for 20 seconds
and then `guide` becomes null. `guide` is the trip in progress, or null. `route` is the planned sign ids
from where they started, `at` is the last sign seen on the way (null until the
first one).

`POST /api/signs` JSON `{"name", "aliases", "note", "say_note"}` → 201 sign. 409 when
all 50 markers are used or the name is taken.
`PATCH /api/signs/<id>` JSON with any of those fields → sign.
`DELETE /api/signs/<id>` → 204; also removes its links and its place on the plan.
`PUT /api/signs/<id>/links` JSON `{"links": [{"to": 5, "text": "..."}]}` → the full
`links` list for every sign. Replaces all directions leaving this sign.
`PUT /api/plan` JSON plan → plan (cleaned: numbers clamped to the plan, unknown
sign ids dropped). 400 with a sentence when it is not a plan.

`POST /api/guide` JSON `{"destination": 5}` → the `guide` object; the wearer
hears the first step at once if a sign was seen in the last 2 minutes,
otherwise "Look around for a sign on the wall." 404 unknown sign.
`DELETE /api/guide` → 204.

`/api/live` also carries `room` and `guide` (same shapes), and `markers`: the
signs in the current frame, `[{"id": 3, "name": "Hallway", "corners": [[x, y] x4]}]`.

New event kinds in `/api/events`: `room` (moved to another room), `guide`
(trip started, step spoken, arrived, stopped, no route).
