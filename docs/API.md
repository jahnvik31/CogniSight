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
  "people": 3
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
