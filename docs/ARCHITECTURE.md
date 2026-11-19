# CogniSight architecture

CogniSight is one Python program that runs on a Raspberry Pi 5 with the Pi
Camera Module 2. Inside a single process, background threads read the camera,
recognise faces, read printed room signs, speak to the wearer, and listen for
voice commands, while a small web server provides an HTTP API, a live camera
stream, and a pre-built caregiver dashboard to phones and computers on the
same network. This document describes how those parts fit together, where data
is kept, how the device is installed and started, and what happens when a part
is missing or fails.

The feature documents go into each part in detail:
[face recognition](features/face-recognition.md),
[speech and voice](features/speech-and-voice.md),
[talking signposts](features/signposts.md),
[the caregiver dashboard](features/caregiver-dashboard.md), and
[approximate location](features/location.md). The HTTP API is specified in
[API.md](API.md).

> **Hardware status.** The program has **not** yet been run on the Raspberry
> Pi. It has been run end to end on a Windows laptop with a USB webcam. The Pi
> camera was confirmed working on the Pi with a separate Picamera2 streaming
> script. Statements in this document about the Pi describe what the code and
> scripts are written to do, not observed results.

---

## 1. Components

```
┌──────────────────── Raspberry Pi 5: one process, "cognisight start" ────────────────────┐
│                                                                                          │
│  Pi Camera Module 2 ─CSI─► camera thread ─► newest-frame slot                            │
│  (USB webcam fallback)     640×480, 15 fps   (lock + condition + frame number)           │
│                            draws boxes,         │               │               │        │
│                            encodes JPEG         ▼               ▼               ▼        │
│                                         recognition thread  sign thread    MJPEG streams │
│                                         DeepFace Facenet512 ArUco 4x4_50   (annotated    │
│                                         + data/faces/       + signs.json    JPEG)        │
│                                                 │           → Navigator         │        │
│                                                 │ names       │ room, steps     │        │
│                                                 ▼             ▼                 │        │
│  microphone ─► Moonshine STT ─► command ─► Announcer (cooldowns)                │        │
│                                 parser ──── "take me to…", "where am I" ─►      │        │
│                                             Navigator                           │        │
│                                                 │                               │        │
│  earphones ◄─ default audio ◄─ moonshine-voice TTS (queue) → espeak-ng → silence│        │
│                                                                                 │        │
│  Flask/Werkzeug HTTP server, port 8765 (main thread) ◄── Runtime state ─────────┘        │
│     /api/…    /stream.mjpg    web/dist (built dashboard)                                 │
│        │            │                                                                    │
│        │            └─ Locator (5-min cache) ─ nmcli Wi-Fi scan                          │
└────────┼────────────────────────┼────────────────────────────────────────────────────────┘
         │ same Wi-Fi network     │ HTTPS
         ▼                        ▼
  caregiver's browser      Google Geolocation API
         │
         │ map tiles (Place page only)
         ▼
  OpenStreetMap tile servers
```

The browser loads map tiles directly from OpenStreetMap on the Place page; it
does not talk to Google. Everything else the browser needs comes from the Pi.

### 1.1 Hardware and software

| Part | Choice |
|---|---|
| Computer | Raspberry Pi 5 (8 GB), Raspberry Pi OS 64-bit with desktop |
| Camera | Raspberry Pi Camera Module 2 (Sony IMX219 sensor) on the 22-pin ribbon cable, through Picamera2; a USB webcam through OpenCV as a fallback |
| Audio | Default system output (Bluetooth earphones once paired and selected); default microphone (a USB microphone is recommended) |
| Language | Python 3.9 or later (`requires-python = ">=3.9"`) |
| Required package | Flask 3 (`Flask>=3.0,<4`) |
| Optional `faces` extra | `deepface>=0.0.93`, `tf-keras>=2.16,<3` (DeepFace brings TensorFlow and `opencv-contrib-python-headless`, which includes the ArUco module) |
| Optional `voice` extra | `moonshine-voice>=0.1.6` |
| Development extra | `pytest>=8,<9` (the tests themselves use the standard `unittest` module) |
| Dashboard | SolidJS, built with Vite; the built files are committed |

`pyproject.toml` warns not to add another OpenCV package: two OpenCV packages
would overwrite the same `cv2` module.

---

## 2. One process, several threads

All of CogniSight runs in **one process**, started by `cognisight start`
(usually through `./start.sh`). A single process was chosen over separate
programs for each part so there is one command to run, one log to read, and no
files or sockets to share between processes. The parts communicate through
one shared object, `Runtime` (in `runtime.py`).

### 2.1 Threads

| Thread | Started by | What it does | Rate |
|---|---|---|---|
| **Main thread: HTTP server** | `cli._start()` → `server.serve()` | Werkzeug's `make_server(host, port, app, threaded=True)` serves the API, the MJPEG stream, and the dashboard. Each request runs in its own short-lived thread; each open camera stream keeps one thread busy for as long as it is watched. | On demand |
| **`_camera_loop`** | `Runtime.start()` | Opens the camera, reads frames as fast as it delivers them, draws boxes and labels on a copy, encodes that copy as JPEG (quality 80), and publishes the raw frame and the JPEG. Reopens the camera after errors. | The camera's frame rate (15 fps configured for the Pi camera) |
| **`_recognition_loop`** | `Runtime.start()` | Loads DeepFace, then repeatedly names the faces in the newest frame and informs the announcer and the timeline. | At most 2 passes per second (`--interval 0.5`) |
| **`_sign_loop`** | `Runtime.start()` | Reads sign markers in the newest frame and moves the Navigator. | At most about 4 passes per second (0.25 s pause) |
| **`_voice_setup`** | `Runtime.start()` | Waits for TensorFlow to finish loading, then loads speech and starts listening. Ends when done. | Once |
| Library threads | moonshine-voice | The text-to-speech queue and playback, and the microphone transcriber, which calls `Runtime._on_heard()` once per finished line of speech. | — |
| Child process | `EspeakSpeaker` | `espeak-ng`, only when the fallback voice is in use. | Per sentence |

All of CogniSight's own threads are daemon threads, so they end when the main
thread ends. On Ctrl+C, the server stops and `Runtime.close()` sets the stop
flag, stops the listener, and closes the camera.

### 2.2 How the threads share frames

The camera thread produces frames; the recognition thread, the sign thread,
and every MJPEG stream consume them. They share one slot holding **only the
newest frame**, protected by a lock and a condition variable:

```python
self._lock = threading.Lock()
self._frame_ready = threading.Condition(self._lock)
self._frame = None         # newest raw frame (numpy array, BGR)
self._jpeg = None          # newest annotated JPEG
self._frame_number = 0     # increases by 1 for every new frame
```

**Producer.** After reading and annotating a frame, the camera thread takes
the condition's lock, stores the frame and its JPEG, increments
`_frame_number`, and calls `notify_all()` to wake every waiting consumer.

**Consumers.** Each consumer remembers the number of the last frame it
processed and waits until the number changes:

```python
with self._frame_ready:
    self._frame_ready.wait_for(lambda: self._frame_number != last or self._stop.is_set(), timeout=2)
    frame = self._frame
    last = self._frame_number
```

This design has several consequences:

- **No busy waiting**: consumers sleep until a new frame exists.
- **Always the newest frame, never a backlog**: there is no queue. A consumer
  that is slower than the camera (face recognition is much slower than 15 fps)
  simply skips the frames that arrived while it was busy. Results are never
  more than one pass behind the live picture.
- **Independent consumers**: the sign thread does not wait for the recognition
  thread or the other way round, so slow face recognition does not slow sign
  reading, and a failure in one does not stop the other.
- **Timeouts** (2 seconds for recognition and signs, 5 seconds for streams) let
  each loop notice the stop flag, and let a stream end when the camera has
  gone.
- **No copying for readers**: each camera read returns a new array, and nobody
  modifies a published frame (drawing is done on a copy, and enrolment copies
  the frame before encoding it), so consumers can use the shared array
  directly.

The same `_lock` also protects the latest faces, the latest markers, and the
event list. The camera thread copies the faces and markers under the lock
before drawing them, so boxes on the picture are those of the most recent
recognition and sign passes.

Other locks: the gallery's re-entrant lock and DeepFace's TensorFlow lock (see
[face recognition, section 8](features/face-recognition.md#8-thread-safety)),
the sign store's and Navigator's re-entrant locks, the announcer's lock for its
table of when each person was last seen, and the locator's lock that allows one location lookup at a
time.

### 2.3 Events

`Runtime.event(kind, name, text)` adds an entry to a timeline kept in memory: a
double-ended queue of at most **300** events, newest first, each with an
increasing id and a Unix time. `GET /api/events?limit=N` returns the newest N
(1–300, default 50). Kinds: `system`, `seen`, `unknown`, `said`, `heard`,
`room`, and `guide`. The timeline is not saved and starts empty on every
start-up.

---

## 3. Start-up order

`cognisight start` (`cli.main` → `cli._start`) does the following, in order:

1. Parse the command-line options and load `.env` into the environment
   (without overriding variables that are already set).
2. Create the face `Gallery` with a `DeepFaceEmbedder`. Nothing heavy is
   loaded yet; DeepFace is imported only when first used.
3. Create the gallery folder if needed and construct the `Runtime` with:
   the `SignStore` loaded from `signs.json` beside the gallery folder; a camera
   factory carrying `--camera`, `--flip`, and `--swap-colors`; the recognition
   interval; and the speech and listening options. The runtime starts with a
   silent placeholder speaker ("Loading speech…") and creates the Navigator.
4. `Runtime.start()`:
   1. **Imports `numpy` and `cv2` on the main thread**, before any thread
      starts. The code comment explains why: numpy and OpenCV break when two
      threads import them at the same time, and three of the threads about to
      start use them. Importing them first means later imports in the threads
      only fetch the already-loaded modules. A missing module is ignored here
      (the thread that needs it reports the problem).
   2. Starts the four threads: camera, recognition, signs, voice set-up.
   3. Records the event "CogniSight started".
5. Check for the built dashboard in `web/dist/index.html`; if missing, print a
   warning and serve only the API.
6. Create the Flask app with a `Locator` for location.
7. Print the dashboard addresses: `http://localhost:8765`, then
   `http://<hostname>.local:8765` and `http://<IP address>:8765` (the address
   is found by "connecting" a UDP socket to `10.255.255.255`, which sends no
   packet but reveals which local address would be used).
8. Serve HTTP on `0.0.0.0:8765` until Ctrl+C.

### 3.1 What happens in the threads after start-up

```
time ─────────────────────────────────────────────────────────────────────────►
camera:       open camera ── frames ── frames ── frames ── frames ── frames …
signs:        create ArUco detector ── read signs in every new frame …
recognition:  import TensorFlow + DeepFace, load Facenet512, refresh cache ──┐
                                                                             ├─ "Face recognition ready"
                                                                             └─ name faces in every new frame …
voice setup:  wait for recognition to finish loading (≤180 s) ───────────────┘── load speech ── start listening ── (ends)
```

**Speech loads only after TensorFlow.** The voice thread waits for the
recognition thread to signal that loading has finished (successfully or not),
for at most 180 seconds. The code comment gives the reason: two large
libraries importing at the same time on the Pi is slow and fragile. Until then
the announcer has the silent placeholder speaker. Listening starts only after
speech has loaded, so the device does not listen before it can answer.

Because the camera and sign threads do not wait for anything, the camera
picture and sign reading are available within moments of start-up, before
face recognition is ready.

---

## 4. Data storage

All persistent data is in ordinary files on the Pi's storage. There is no
database.

| Path | Contents | Written by | In git? |
|---|---|---|---|
| `data/faces/<Name>/` | One folder per person; their photos (`.jpg`, `.jpeg`, `.png`, `.webp`). The photos are the record of who the device knows. | Dashboard, `cognisight enroll`, or copying files by hand | No (`/data/` is ignored) |
| `data/faces/<Name>/about.json` | `{"relationship", "note"}` | Dashboard, `enroll` | No |
| `data/faces/.cognisight-embeddings.json` | Cache of one 512-number Facenet512 vector per photo, keyed by `Name/file`, with each photo's modification time and size. Rebuilt automatically; safe to delete. Written via a `.tmp` file and an atomic rename. | Recognition and enrolment | No |
| `data/signs.json` | Signs, the directions between them, and the floor plan. Written via `data/signs.tmp` and an atomic rename. | Dashboard (Home and Sign pages) | No |
| `.env` | `GEOLOCATION_API_KEY=…` | The installer (from `.env.example`), then the caregiver | No (`.env` is ignored) |
| `.models/deepface/` | DeepFace's downloaded weights (Facenet512, about 95 MB) and detector files, kept inside the checkout so they are deleted with it (`DEEPFACE_HOME`). | `cognisight download`, or first use | No (`.models/` is ignored) |
| moonshine-voice cache | The speech and listening models, in the library's own per-user cache directory (outside the repository). | `cognisight download`, or first use | — |
| `web/dist/` | The built dashboard. | Developers (`npm run build`) | **Yes**, on purpose |
| `camera-check.jpg` | One frame saved by the installer's camera check. | `setup.sh` / `cognisight camera` | No |

**Kept only in memory** (lost on restart): the event timeline, each person's
and each sign's "last seen" time, the current room and any trip in progress,
the announcer's and Navigator's introduction and announcement timers, the last sentence said and
the last command heard, and the last location result.

The `--gallery` option moves the face folder; `signs.json` always sits in the
gallery folder's parent.

---

## 5. Modules in `src/cognisight`

| Module | Responsibility | Main contents |
|---|---|---|
| `__init__.py` | Package marker. | `__version__ = "0.3.0"` |
| `camera.py` | Camera input. | `PiCamera` (Picamera2: 640 × 480, `RGB888`, `FrameRate` 15; optional 180° rotation through a libcamera `Transform` with horizontal and vertical flip; optional red/blue swap; label from the sensor model, such as `imx219`), `UsbCamera` (OpenCV `VideoCapture`, optional 180° flip), `open_camera()` (the Pi camera if Picamera2 reports one, otherwise the numbered USB camera), and `save_snapshot()` for the camera check. Picamera2's `RGB888` format is stored as blue, green, red in memory, which is the order OpenCV and DeepFace expect, so no conversion is done; `--swap-colors` exists in case faces look blue on a particular Pi. |
| `faces.py` | People and face recognition. | `Gallery` (folders, `about.json`, the embedding cache, `match`, `identify`), `DeepFaceEmbedder` (lazy DeepFace import, TensorFlow lock, "no face" filtering), `cosine_distance`, `drop_nested`, `NoFaceError`, name and file-name validation, and the constants `MODEL = "Facenet512"`, `DETECTOR = "opencv"`, `THRESHOLD = 0.30`. |
| `signs.py` | Talking signposts. | `SignStore` (signs, links, plan, `route()` breadth-first search, `find_destination()`), `Navigator` (room tracking, arrival announcements, trips), `MarkerDetector` (ArUco `DICT_4X4_50`, minimum side 24 px), `the()` wording, and the timing constants. |
| `voice.py` | Speech and commands. | `introduction()`, `parse_command()`, `Announcer` (introduces a person on first recognition and again only after 120 seconds out of view; records nothing while speech cannot be heard, `can_speak()`; reports what was said), `MoonshineSpeaker`, `EspeakSpeaker`, `NullSpeaker`, `load_speaker()` (fallback chain), `Listener` (Moonshine streaming STT), `download_voice_models()`. |
| `location.py` | Approximate location. | `parse_nmcli()`, `scan_wifi()`, `post_json()`, `lookup()` (Google request and `wifi`/`ip` labelling), `Locator` (key, 5-minute cache). |
| `runtime.py` | The running device. | `Runtime`: the threads, frame sharing, annotation, recognition-to-speech logic, sign loop, voice set-up and command handling, events, and the status and live summaries used by the API; `device_urls()`; `CameraUnavailable`. |
| `server.py` | HTTP. | `create_app()` (every API route, the MJPEG stream, the dashboard files and fallback, the 15 MB upload limit) and `serve()`. |
| `cli.py` | Command line. | `main()` with the `start`, `camera`, `enroll`, `identify`, and `download` commands; `load_env()`. Installed as the `cognisight` command. |

Imports are arranged so that the heavy libraries (TensorFlow, DeepFace,
OpenCV, Picamera2, moonshine-voice) are imported only inside the functions
that use them. As a result the server, the stores, and all 55 automated tests
run with only Flask installed.

---

## 6. HTTP API summary

The device serves everything on port **8765**. All times are Unix seconds.
Errors are JSON objects `{"error": "a plain sentence"}` with a 4xx or 5xx
status. The full specification with example bodies is [API.md](API.md).

| Method and path | Purpose |
|---|---|
| `GET /stream.mjpg` | Live MJPEG stream with boxes and names drawn (503 without a camera). |
| `GET /api/snapshot.jpg` | One annotated JPEG frame. |
| `GET /api/live` | Camera on/off, frame size, faces (name, relationship, distance, box), time of the last recognition pass, last sentence said, current room, trip, and signs in view. |
| `GET /api/events?limit=50` | The timeline, newest first. |
| `GET /api/status` | Host name, dashboard addresses, uptime, and the state of the camera, recognition, speech, listening, people, and signs. |
| `POST /api/speech` | Turn speech on or off. |
| `POST /api/speech/test` | Speak a test sentence. |
| `POST /api/listening` | Turn listening on or off. |
| `GET /api/people` | Everyone saved. |
| `POST /api/people` | Add a person with a first photo (uploaded, or captured from the camera when no file is sent). |
| `GET`, `PATCH`, `DELETE /api/people/<name>` | Read, edit (relationship, note), or delete a person. |
| `POST /api/people/<name>/photos` | Add a photo (uploaded or captured). |
| `GET`, `DELETE /api/people/<name>/photos/<file>` | Fetch or delete one photo. |
| `GET /api/home` | All signs, links, the floor plan, the current room, and the trip. |
| `POST /api/signs`; `PATCH`, `DELETE /api/signs/<id>` | Create, edit, or delete a sign. |
| `PUT /api/signs/<id>/links` | Replace the directions leaving a sign. |
| `PUT /api/plan` | Save the floor plan (cleaned and clamped by the server). |
| `POST /api/guide`; `DELETE /api/guide` | Start a trip to a sign; stop the trip. |
| `GET /api/location`; `POST /api/location/refresh` | Approximate location (an answer is cached 5 minutes, an error 30 seconds); force a new lookup. |

Any other `/api/...` path returns 404 "No such API route.". Any other path
returns the dashboard's `index.html`, so the dashboard's own routes work when
opened directly.

---

## 7. Command-line interface

The `cognisight` command (in `.venv/bin/` after setup) has five subcommands.
`--gallery` (default `data/faces`), `--threshold` (default 0.30), and
`--detector` (default `opencv`) apply to `start`, `enroll`, and `identify`.

| Command | What it does | Options |
|---|---|---|
| `cognisight start` | Runs everything: camera, recognition, signs, speech, listening, and the dashboard. | `--host` (default `0.0.0.0`), `--port` (8765), `--camera N` (USB camera number, used only when there is no Pi camera; default 0), `--flip` (rotate 180°), `--swap-colors` (swap red and blue), `--interval` (seconds between recognition passes; 0.5), `--no-speech` (start with speech off), `--no-listen`, `--listen-model tiny\|small\|medium` (default tiny). |
| `cognisight camera` | Saves one frame and prints the camera type, name, and size, for example `picamera2 (imx219) 640x480 -> camera-check.jpg`. Exits with status 1 and "Camera check failed: …" on error. | `--output` (default `camera-check.jpg`), `--camera`, `--flip`. |
| `cognisight enroll NAME IMAGE` | Adds a photo of a person, creating them if needed. | `--relationship`, `--note` (used only when creating). |
| `cognisight identify IMAGE` | Prints each face in a photo as a name and distance, or "unknown". Exit status 0 if anyone was recognised. | — |
| `cognisight download` | Downloads every model so the device works offline: the Facenet512 weights (printed as about 95 MB), then the OpenCV face detector (by embedding a blank 160 × 160 image), then the speech voice and the tiny listening model. A speech download failure is reported but does not fail the command. | `--no-voice` (skip the speech models). |

---

## 8. Installation and start-up scripts

### 8.1 `setup.sh` (run once)

`./setup.sh` is written for a Raspberry Pi 5 running 64-bit Raspberry Pi OS. It
stops at the first failing command (`set -euo pipefail`). Step by step:

1. **Refuses to run as root.** It must be run as the normal user and asks for
   the password through `sudo` when needed, so the files it creates belong to
   that user.
2. **System packages** (`apt-get update`, then `apt-get install`):
   `python3-venv` and `python3-pip` (the Python environment), `libportaudio2`
   (the audio input/output library used by the speech package), `espeak-ng`
   (the fallback voice), and `curl` (used by `start.sh` to wait for the
   server).
3. **The Pi camera library**, `python3-picamera2`, from Raspberry Pi OS's own
   package repository; Picamera2 is not installed from pip. If it is not
   available, the script warns "The Pi camera will not work; a USB webcam still
   will." and continues.
4. **The Python environment** in `.venv`, created with
   `python3 -m venv --system-site-packages .venv` (only if it does not exist),
   then `pip` and `wheel` are upgraded. **`--system-site-packages`** makes
   packages installed by apt, Picamera2 and its libcamera bindings in
   particular, visible inside the environment; without it, `import picamera2`
   would fail in the environment even though Picamera2 is installed.
5. **The numpy constraint.** The script asks the system Python which major
   version of numpy it has. Raspberry Pi OS Bookworm ships numpy 1.x, and the
   apt build of Picamera2 (with its compiled dependencies) is built against
   it. Because the environment sees system packages but prefers its own, a
   numpy 2 installed into the environment would be imported by Picamera2 in
   place of the system numpy, and compiled code built for numpy 1.x cannot
   load with numpy 2; the script's comment states that installing numpy 2
   "breaks Picamera2". So, **only when the system numpy is 1.x**, the script
   writes a pip constraints file:

   ```
   numpy<2
   opencv-contrib-python-headless<4.12
   pandas<3
   ```

   The OpenCV and pandas limits are there to keep pip from choosing newer
   releases of those packages that would require numpy 2 (the script's
   comment explains only the numpy limit). On a system whose numpy is already
   2.x, or where none is found, the constraints file is left empty.
6. **Installs CogniSight** in editable mode with both optional extras:
   `pip install -c <constraints> -e ".[faces,voice]"`, which brings DeepFace,
   TensorFlow, OpenCV, and moonshine-voice. The script warns that this takes 10
   to 20 minutes.
7. **Creates `.env`** from `.env.example` if it does not exist, and tells the
   user to put the Google Geolocation key in it.
8. **Creates `data/faces`.**
9. **Downloads the models** with `.venv/bin/cognisight download`, so the demo
   works without an internet connection (except location).
10. **Checks the camera** with `.venv/bin/cognisight camera --output
    camera-check.jpg`. On success it says to open the image; on failure it
    warns to check the ribbon cable ("contacts facing the right way") and
    continues.
11. **Autostart, if requested.** With `./setup.sh --autostart`, it writes
    `~/.config/autostart/cognisight.desktop`, a desktop-session autostart entry
    that runs `lxterminal -e <repo>/start.sh` when the Pi's desktop starts, so
    CogniSight starts with a visible terminal showing its output. Deleting that
    file turns autostart off.
12. Prints "Setup finished. Run ./start.sh".

Whether this dependency set installs and runs correctly on the Pi has not yet
been verified.

### 8.2 `start.sh` (every time)

1. Checks that `.venv/bin/cognisight` exists; otherwise prints "CogniSight is
   not installed yet. Run ./setup.sh first." and exits.
2. If a desktop display is present (`DISPLAY` or `WAYLAND_DISPLAY` is set) and
   `COGNISIGHT_NO_BROWSER` is not `1`, starts a background helper that polls
   `http://localhost:8765/api/status` once a second for up to 90 seconds and,
   as soon as the device answers, opens the dashboard full-screen in app mode
   with `chromium-browser` (or `chromium`, or else `firefox`).
3. Replaces itself with `cognisight start --port 8765`, passing on any extra
   options (for example `./start.sh --flip`).

### 8.3 Optional service

`deploy/cognisight.service` is a systemd **user** service for running
CogniSight without the desktop: it runs `~/CogniSight/.venv/bin/cognisight
start` from `~/CogniSight`, after the network, sound, and PipeWire are up,
restarts it 5 seconds after a failure, and logs to the journal
(`journalctl --user -u cognisight -f`). It assumes the repository is cloned to
`~/CogniSight`. Installation instructions are in the file's comments. It has
not been tested on the Pi.

---

## 9. Failure handling

The runtime's design rule, stated in its docstring, is that nothing raises when
the camera, DeepFace, or audio is missing: each part reports its error in
`/api/status` and keeps retrying where that makes sense, and the dashboard
explains the problem in plain words.

| Missing or failing part | What the device does | What the caregiver sees |
|---|---|---|
| **No camera at start-up** (no Picamera2 camera and no USB camera) | The camera thread records "Camera not found: …" and retries every **5 seconds**. Recognition and signs wait for frames. `/stream.mjpg` and `/api/snapshot.jpg` return 503; adding a person with the device camera returns 503 "Could not take a photo: …" and saves nothing. | "Camera off" in the header; the camera area says "The camera isn't running. Check the ribbon cable and restart CogniSight. Trying again every 5 seconds."; the Device page shows the error. |
| **Camera stops delivering frames** | "Camera stopped: …", event "Camera stopped. Retrying.", the camera is closed and reopened after **2 seconds**. Open streams end and the dashboard reconnects. | As above, until it recovers; then "Camera ready (…)" on the timeline. |
| **DeepFace or TensorFlow missing, or the model fails to load** | The recognition thread records "Face recognition could not start: …" and stops (no retry). Speech loading is released immediately. Camera, signs, speech, and the dashboard keep working. Adding a photo fails with "Could not read that photo: Face recognition is not installed. Run ./setup.sh again." | Device page: Recognition "Not running" with the reason. |
| **A recognition pass fails** | "Recognition failed: …"; that pass finds no faces; the next pass tries again. | Device page error until a pass succeeds. |
| **OpenCV without the ArUco module** | The sign thread records "Signs need OpenCV with the ArUco module: …" and stops. | Timeline entry; `signs.ok` false in `/api/status`. |
| **moonshine-voice missing or its voice fails** | `espeak-ng` is used; if that is missing too, speech is silent. | Device page: Speech "Not available" (or available with "Using espeak-ng because …"). |
| **Audio output fails while speaking** (for example, Bluetooth disconnects) | The announcer stores "Could not play speech: …" and carries on. | The error on the Live and Device pages. |
| **No microphone** | Listening is marked unavailable with "Listening unavailable: …". Turning listening on again (from the Device page or `POST /api/listening`) retries opening the microphone. | Device page: Listening "Not available"; the toggle stays enabled so a microphone plugged in later can be tried without restarting. |
| **A sign detection pass fails** | "Reading signs failed: …"; that frame counts as having no signs; the error is cleared by the next successful pass. | `signs.ok` false in `/api/status` until a pass succeeds. |
| **No network for the dashboard** | The device keeps working on its own (recognition, speech, and signs do not need the network). | The dashboard shows "Can't reach the device. Retrying…" and recovers by itself. |
| **No internet** | Speech and recognition use the models downloaded during setup and work offline. Location reports "Could not reach Google: …". Map tiles do not load. | Place page: "The last location check failed. …"; "The map can't load without an internet connection." |
| **No location key** | No scan, no request. | Place page: "Location isn't set up yet" with steps. |
| **Dashboard not built** | The API still runs; a warning is printed. | The browser gets no dashboard. |
| **Corrupt or unreadable `signs.json`, `about.json`, or embedding cache** | Treated as empty (signs) or as empty fields (about), or rebuilt from the photos (cache). | — |
| **Upload too large or not a photo** | 413 "That photo is larger than 15 MB. Use a smaller one."; 400 "Use a JPG, PNG, or WebP photo." | The message next to the form. |

---

## 10. Testing

There are 55 automated tests in `tests/` (11 for faces, 7 for location, 11
for the server and API, 18 for signs and guidance, 8 for voice). They use fake
cameras, fake embedders (vectors stored as text files), fake speakers, and
injected clocks, so they need neither a camera nor DeepFace; the one test that
reads a generated marker image is skipped when OpenCV is not installed. Run
them with `python -m unittest discover -s tests -v`. A GitHub Actions workflow
(`.github/workflows/software-checks.yml`) installs the package with only Flask
on Ubuntu 24.04 and Python 3.11, runs the tests, and builds the dashboard with
Node 22, on every push and pull request. The evidence for each feature, and
what has not yet been verified on the Pi, is collected in
[TESTING.md](TESTING.md).

---

## 11. Security and privacy

### 11.1 Properties of the design

- **On-device processing.** Face detection and recognition, speech synthesis,
  and speech recognition run on the Pi. Photos, face vectors, audio, and
  transcripts are never sent anywhere.
- **No audio is recorded.** The microphone stream is transcribed by the
  library as it arrives; CogniSight keeps only the text of the last
  recognised command. Unrecognised speech is discarded and not logged.
- **Strangers are not stored.** Unknown faces are embedded to be compared,
  then discarded; no photo or vector of them is saved, and they are never named.
  Photos are taken only when a caregiver asks.
- **Only people a caregiver adds can be named**, and the strict 0.30 cutoff
  favours saying nothing over naming the wrong person.
- **The wearer can silence the device** with one word ("stop").
- **The location key stays on the Pi.** It is read from `.env` (excluded from
  git) and used only in the Pi's own HTTPS request to Google; no API response
  contains it. What the location lookup sends to Google, and what the map sends
  to OpenStreetMap, is listed in [location.md](features/location.md#7-privacy).
- **Input checking.** Person names cannot contain path separators or start
  with a dot, photo file names are reduced to a bare name with an allowed
  suffix, and static files are served only from inside `web/dist`, so requests
  cannot read or write files outside their folders. Uploads are limited to
  15 MB and to JPG, PNG, and WebP. The floor plan is rebuilt from validated
  values rather than stored as sent.
- **Private data is excluded from git**: `data/`, `.env`, `.models/`, and
  `.venv` are all ignored.

### 11.2 Limitations

- **No login.** The dashboard and API have no authentication. Anyone who can
  reach the Pi on the network can watch the live camera, see and download every
  saved photo, add or delete people and signs, start guidance, and turn speech
  or listening off. The server listens on all network interfaces
  (`0.0.0.0`). This is acceptable for a demonstration on a trusted network, not
  for real use. A caregiver login and HTTPS are listed as future work.
- **No encryption in transit.** The dashboard uses plain HTTP, so traffic on
  the local network (including the camera stream and photos) can be observed by
  others on that network.
- **Cross-site requests.** Because there is no login or request token, a web
  page opened on the same network could make the browser send simple form
  requests to the device. Browsers block such pages from reading the answers
  and from sending JSON requests without the server's consent, but a
  multipart form post, such as adding a person, is not blocked.
- **No encryption at rest.** Photos and `signs.json` are ordinary files on the
  Pi's storage card; anyone with the card can read them.
- **Consent.** The camera processes the faces of everyone in view, including
  visitors who have not been enrolled. The device does not store them, but
  its use around other people should be agreed with them.
