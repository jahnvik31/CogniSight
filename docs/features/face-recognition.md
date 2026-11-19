# Contextual face recognition

CogniSight watches the camera picture, finds every face in it, and compares each
face with photos of the people a caregiver has added. When a face matches a
known person closely enough, the wearer hears who it is and how they are
related ("This is Priya, your daughter."), and the caregiver dashboard draws a
green box with the name. Faces that do not match anyone are marked "Unknown" on
the dashboard but are never named or announced.

The code is in `src/cognisight/faces.py` (the gallery, embeddings, and
matching) and `src/cognisight/runtime.py` (the recognition loop and events).
The tests are in `tests/test_faces.py` and `tests/test_server.py`.

> **Hardware status.** None of the recognition pipeline has been run on the
> Raspberry Pi yet. The Pi camera itself was confirmed working with a separate
> Picamera2 streaming script. Recognition speed on the Pi's CPU is unknown.

---

## 1. The gallery: one folder per person

People are stored as plain folders of photos. There is no database. By default
the gallery root is `data/faces/` inside the repository (the `--gallery` option
changes it).

```
data/faces/
├── .cognisight-embeddings.json      ← cache, rebuilt automatically (section 6)
├── Priya/
│   ├── about.json
│   ├── capture-1763540000.jpg       ← taken with the device camera
│   └── photo-1763540100.jpg         ← uploaded from a phone or computer
└── Ravi/
    ├── about.json
    └── photo-1763541000.png
```

The **photos are the record**. Everything else (the embedding vectors) is a
cache derived from them. A folder of photos copied in by hand is picked up
automatically on the next recognition pass, even without an `about.json` (this
is covered by the test `test_hand_copied_photo_folder_is_picked_up`).

### 1.1 Folder and file rules

| Item | Rule (from `faces.py`) |
|---|---|
| Person name (folder name) | Whitespace is collapsed to single spaces. Must be 1–80 characters, must not be `.` or `..`, must not start with a dot, and must not contain `/`, `\`, `:` or a NUL character. Error messages: "Enter a name of up to 80 characters.", "A name cannot start with a dot.", "A name cannot contain / \ or :". |
| Photo types | `.jpg`, `.jpeg`, `.png`, `.webp` (case-insensitive). Anything else in the folder is ignored. |
| Hidden files | Files and folders whose names start with `.` are ignored (this is how the cache file and any temporary files stay out of the people list). |
| Photo file names | `{stem}-{unix time}{suffix}`, where the stem is `capture` for a photo taken with the device camera and `photo` for an upload or a command-line enrolment. If that name exists, `-2`, `-3`, … up to `-999` is appended. |
| Duplicate names | Creating a person whose folder already exists fails with "Priya is already saved." (HTTP 409 from the API). |
| Photo names in URLs | `photo_filename()` accepts only a bare file name with a photo suffix that does not start with a dot, so a request such as `../../x.jpg` is refused. |

People are listed in case-insensitive alphabetical order of folder name.

### 1.2 `about.json`

Each person may have an `about.json` beside their photos:

```json
{
  "relationship": "daughter",
  "note": "Visits on Sundays."
}
```

- `relationship` is what the wearer hears after the name. It is stored with
  whitespace collapsed and cut to 80 characters.
- `note` is a free-text reminder, trimmed and cut to 500 characters. It is
  spoken only when the wearer asks "tell me more" (see
  [Speech and voice](speech-and-voice.md)).

If the file is missing, unreadable, or not a JSON object, both fields are
treated as empty strings. Nothing else is stored about a person.

---

## 2. Enrolment: adding a person or a photo

There are three ways to add a photo. All of them end in the same function,
`Gallery.add_photo()`, which enforces one rule: **a photo in which no face can
be found is refused and not kept.**

### 2.1 How `add_photo` works

1. The bytes are written to a new file in the person's folder (section 1.1
   naming).
2. The file is passed to the embedder (section 3). If the embedder raises an
   error, the file is deleted and the error is passed on.
3. If the embedder finds faces, the **largest face** (by box area, width ×
   height) is taken to be the person the portrait is of, and its vector is
   stored in the cache.
4. If it finds no face, the file is deleted and `NoFaceError` is raised with
   the message "No face was found in that photo. Use a clear, well-lit photo
   facing the camera."

This means the gallery cannot silently fill up with pictures that would never
match anyone.

### 2.2 Dashboard: take a photo with the device camera

On the People page ("Add a person") and on a person's own page ("Take photo
with the device camera"), the caregiver sees the live camera picture and
presses a button. The browser sends the form **without a file**. The server
then calls `Runtime.capture()`, which copies the newest raw camera frame (the
one without boxes drawn on it) and encodes it as JPEG at quality 92. That JPEG
is saved with the stem `capture`.

If the camera is not running, `capture()` raises `CameraUnavailable` and the
API answers HTTP 503 "Could not take a photo: …". Nothing is saved.

### 2.3 Dashboard: upload a photo

The caregiver can instead choose a file ("Upload a photo", or "Take photo with
this phone", which opens the phone's front camera through the file picker on
touch devices). Before uploading, the browser shrinks the photo
(`prepareImage()` in `web/src/lib.js`): if its longer side is over 1600 pixels,
or it is larger than 2.5 MB, or it is not a JPEG/PNG/WebP, it is redrawn so the
longer side is at most 1600 pixels and re-encoded as JPEG at quality 0.9. This
is done so the Pi spends less time on large phone photos. If the browser cannot
decode the image, the original file is sent unchanged.

The server accepts uploads of up to 15 MB (`MAX_UPLOAD_BYTES`); larger requests
get HTTP 413 "That photo is larger than 15 MB. Use a smaller one." Files with a
suffix other than the four photo types get HTTP 400 "Use a JPG, PNG, or WebP
photo."

### 2.4 What happens when the first photo has no face

When a **new person** is created through `POST /api/people`, the server first
creates the folder and `about.json`, then adds the photo. If adding the photo
fails for any reason (no face, or the photo cannot be read), the server
**deletes the whole person again**, so no half-saved person is left behind. The
API returns HTTP 400 with the "No face was found…" sentence, or "Could not read
that photo: …" for other errors. This behaviour is tested by
`test_no_face_photo_leaves_no_half_saved_person`.

When a photo is added to an **existing person** (`POST
/api/people/<name>/photos`), only that photo is rejected; the person and their
other photos are untouched.

### 2.5 Command line

```sh
.venv/bin/cognisight enroll "Priya" a.jpg --relationship daughter --note "Visits on Sundays."
```

If the person does not exist, they are created with the given relationship and
note; if they already exist, the photo is added and the `--relationship` and
`--note` options are ignored. A photo without a face prints the "No face was
found…" message and exits with status 1. As with the API, a person created by
this command is deleted again if their first photo is refused, so no empty
person folder is left behind. (A photo refused for an existing person leaves
that person untouched.)

### 2.6 Advice given to the caregiver

The dashboard says that 3–5 photos from slightly different angles make
recognition steadier. A person with fewer than three photos is shown "Add N
more photo(s) for steadier recognition.", and a person with none is shown
"There are no photos yet, so CogniSight can't recognise them." When taking a
device photo, the caregiver is asked to have the person face the camera from
about an arm's length away, in good light, and to turn their head a little
between photos. These are recommendations; the number of photos is not
enforced.

---

## 3. Embeddings: DeepFace, Facenet512, and the OpenCV detector

### 3.1 The model and detector

Recognition uses the DeepFace library (`deepface>=0.0.93` in `pyproject.toml`;
version 0.0.105 was installed in the development environment). The settings
are constants in `faces.py`:

| Setting | Value | Meaning |
|---|---|---|
| `MODEL` | `"Facenet512"` | The recognition network. It turns a face crop into a vector of 512 numbers (an *embedding*, or "signature"). Faces of the same person give vectors that point in similar directions. |
| `DETECTOR` | `"opencv"` | DeepFace's OpenCV face detector backend. In the installed DeepFace version this is OpenCV's Haar-cascade frontal-face detector, with a second Haar cascade for the eyes that DeepFace uses to level the face before embedding. It can be changed with `--detector` (for example to another backend DeepFace supports); only `opencv` has been used by the project. |
| `align` | `True` | DeepFace rotates the crop so the eyes are level when it can find them. |
| `normalization` | `"base"` | DeepFace's default input normalisation. |
| `enforce_detection` | `False` | DeepFace does not raise an error when it finds no face (see 3.3). |

The model weights (about 95 MB, as printed by `cognisight download`) are
downloaded once into `.models/deepface/` inside the repository. The code sets
the `DEEPFACE_HOME` environment variable to that folder (only if it is not
already set) and sets `TF_CPP_MIN_LOG_LEVEL=2` to quieten TensorFlow's log
output.

### 3.2 Lazy loading

`DeepFaceEmbedder` imports DeepFace (and therefore TensorFlow) only the first
time it is used, inside `load()`. This keeps the rest of the program, the
dashboard, and the automated tests usable on a machine without DeepFace: the
tests replace the embedder with a fake one that reads vectors from text files.
If DeepFace is not installed, `load()` raises "Face recognition is not
installed. Run ./setup.sh again." After importing, `load()` calls
`DeepFace.build_model("Facenet512")` so the weights are in memory before the
first frame arrives.

### 3.3 One call per image, and the "no face" sentinel

`DeepFaceEmbedder.embed(image)` accepts either a file path (enrolment) or a
camera frame as a BGR array (recognition), and calls `DeepFace.represent()`
once. DeepFace returns one row per detected face, each with a `facial_area`
(`x`, `y`, `w`, `h`), a `face_confidence`, and the 512-number `embedding`.

Because `enforce_detection` is off, DeepFace does not report "no face" as an
error. Instead it returns a single row that covers **the whole image** with a
confidence of zero. If this row were kept, an empty picture would be embedded
and compared with the gallery as if it were a face. `embed()` therefore
discards:

- any row whose `face_confidence` is zero or missing **and** whose box starts
  at the image origin (x = 0 and y = 0), which is the shape of that sentinel;
  and
- any row whose box has zero or negative width or height.

If `represent()` raises a `ValueError` (DeepFace's error for images it cannot
process), `embed()` returns an empty list. The result is a list of `(box,
vector)` pairs, one per real face.

---

## 4. Matching: cosine distance and the 0.30 cutoff

### 4.1 Cosine distance

Two vectors are compared with **cosine distance** (`cosine_distance()` in
`faces.py`):

```
distance(a, b) = 1 − (a · b) / (‖a‖ × ‖b‖)
```

It is 0 when the vectors point the same way, 1 when they are at right angles,
and up to 2 when they point in opposite directions. Only the direction matters,
not the length. If either vector has zero length, the distance is defined as
1.0.

### 4.2 Best photo per person

`Gallery.match(vector, known)` compares one face with **every usable photo of
every person**. For each person it keeps their **smallest** distance over all
of their photos. The person with the smallest of those is the candidate. This
"best of photos" rule is why more photos from different angles make
recognition steadier: a face turned slightly to the left only has to resemble
one of the person's photos well, not their average.

### 4.3 The cutoff

The candidate is accepted only if their best distance is **0.30 or less**
(`THRESHOLD = 0.30`; a distance exactly equal to 0.30 is accepted, because the
code rejects only `distance > threshold`). Otherwise the face is "unknown" and
both the name and the distance are `None`. Accepted distances are rounded to 4
decimal places for display.

The value 0.30 is the same value DeepFace itself uses as its default cosine
threshold for Facenet512 (in `deepface/config/threshold.py` of the installed
version). The project chose it after the reference project VISU-X's cutoff of
0.70 was found to be too loose: as recorded in
[PROJECT_OVERVIEW.md](../PROJECT_OVERVIEW.md), two photos of people who were
not in the gallery were wrongly named at distances 0.285 and 0.339 with that
cutoff, while enrolled photos matched at 0.0. The cutoff deliberately favours
saying nothing over naming the wrong person. It has **not** been calibrated on
photos of the actual family members. It can be changed with `--threshold` on
the command line and is shown on the Device page as "Match cutoff".

### 4.4 Worked example

Real embeddings have 512 numbers; this example uses two or three so the
arithmetic is visible. The numbers are the ones used in `tests/test_faces.py`.

**The cutoff.** Priya has one photo with the vector (1, 0).

| Face in the camera | Cosine similarity with (1, 0) | Distance | Result |
|---|---|---|---|
| (1, 0.5) | 1 / √1.25 = 0.894 | 0.106 | Named Priya |
| (1, 1) | 1 / √2 = 0.707 | 0.293 | Named Priya (just under 0.30) |
| (0.8, 1) | 0.8 / √1.64 = 0.625 | 0.375 | Unknown |

**Best of photos.** Priya has two photos, (1, 0, 0) and (0, 1, 0); Ravi has one,
(0, 0, 1). A face with the vector (0.05, 1, 0) appears.

| Person | Distance to each photo | Best |
|---|---|---|
| Priya | 0.950 to (1, 0, 0); **0.001** to (0, 1, 0) | 0.001 |
| Ravi | 1.000 to (0, 0, 1) | 1.000 |

Priya's best distance (0.001) is the smallest and is under 0.30, so the face is
named Priya. If her gallery held only the first photo, her best would be 0.950
and the face would be unknown. A second face, (1, 1, 1), is 0.423 from every
photo, so it is unknown.

### 4.5 Every face in the frame

`Gallery.identify(image)` embeds the image, filters overlapping detections
(section 5), and matches each remaining face independently. It returns a list
of `Face(box, name, distance)` records in order of decreasing box size. An
empty gallery names no one.

---

## 5. Filtering overlapping detections (`drop_nested`)

OpenCV's Haar detector sometimes reports a second, smaller "face" on a pillow,
collar, or patterned shirt next to or overlapping a real face. `drop_nested()`
removes these:

1. Sort the detections by box area, largest first.
2. Keep a detection only if, for **every** box already kept, the area where the
   two boxes overlap is at most **15 %** (`limit=0.15`) of the **smaller
   (current) box's** own area.

So a small box that sits mostly over a larger face is dropped, while a second
person elsewhere in the room, whose box does not overlap, is kept. In the test
`test_small_box_overlapping_a_face_is_dropped_but_a_second_person_is_kept`, a
61 × 61 box overlapping a 130 × 130 face is dropped, and a separate 60 × 60 face
is kept.

Two genuinely overlapping faces (for example one person standing partly behind
another) can also be reduced to one by this rule; the smaller face is the one
dropped.

---

## 6. The embedding cache

Embedding a photo takes far longer than reading a few numbers from a file, so
each photo is embedded once and the result is cached in
`data/faces/.cognisight-embeddings.json`. The cache is a JSON object keyed by
`"<person folder>/<file name>"`:

```json
{
  "Priya/capture-1763540000.jpg": {
    "stamp": [1763540000123456789, 48213],
    "vector": [0.0132, -0.0871, "… 512 numbers in total …"]
  },
  "Ravi/photo-1763541000.png": {
    "stamp": [1763541000987654321, 30544],
    "vector": null
  }
}
```

- `stamp` is the photo file's modification time in nanoseconds and its size in
  bytes.
- `vector` is the embedding of the largest face in the photo, or `null` if no
  face was found (for example in a hand-copied photo that was never checked at
  enrolment). A `null` entry is remembered so the photo is not re-embedded on
  every pass; it simply contributes nothing to matching.

### 6.1 When the cache is rebuilt

`Gallery.refresh()` runs at start-up and **at the start of every recognition
pass** (through `known_vectors()`). It:

- embeds any photo with no cache entry, or whose `stamp` no longer matches the
  file (the photo was replaced or edited);
- deletes cache entries for photos that no longer exist;
- writes the cache back only if something changed.

In addition, deleting a photo through the dashboard removes its entry at once,
and deleting a person removes all of their entries. Deleting the cache file is
always safe: it is rebuilt from the photos on the next pass.

The cache is written atomically: the JSON is written to
`.cognisight-embeddings.json.tmp` and then renamed over the real file with
`os.replace`, so a crash mid-write cannot leave a half-written cache.

Because `refresh()` checks every photo's modification time and size on every
pass, a change to the gallery (a new photo, a deleted person, a hand-copied
folder) takes effect on the very next recognition pass, without a restart. The
cost is one file-system `stat` per photo per pass, which is negligible for a
household-sized gallery.

---

## 7. The recognition loop

The loop runs in its own background thread, `_recognition_loop`, inside the
single CogniSight process (see [ARCHITECTURE.md](../ARCHITECTURE.md)).

### 7.1 Start-up

1. Load DeepFace and the Facenet512 weights (`embedder.load()`).
2. Bring the cache up to date (`gallery.refresh()`).
3. Record "Face recognition ready" on the dashboard timeline.

If either step fails (for example, DeepFace is not installed), the error is
shown on the Device page ("Face recognition could not start: …") and the
thread **ends**. Recognition is not retried; the program must be restarted.
The camera, signs, speech, and dashboard keep running. In either case the
thread signals that loading has finished, which lets speech start loading
(speech waits for TensorFlow so the two large libraries do not import at the
same time; see [ARCHITECTURE.md](../ARCHITECTURE.md)).

### 7.2 Each pass

1. Wait until the camera thread has published a **newer frame** than the one
   last processed (up to 2 seconds, then check again). Frames that arrive while
   a pass is running are skipped; recognition always works on the newest frame.
2. Run `gallery.identify(frame)`. If it raises, the error is shown as
   "Recognition failed: …" and the pass is treated as having found no faces;
   the next pass tries again and clears the error if it succeeds.
3. Record how long the pass took. This is reported as `seconds_per_check` on
   the Device page.
4. Publish the faces (for the dashboard, the drawn boxes, and voice commands).
5. Update "seen" and "unknown" events and tell the announcer (7.3, 7.4).
6. Wait `max(interval − elapsed, 0.05)` seconds, where `interval` is 0.5
   seconds by default (`--interval`).

So recognition runs **at most twice a second**. If a pass takes longer than the
interval, the loop pauses only 0.05 seconds before the next one. How long a
pass takes on the Pi's CPU has not been measured.

### 7.3 "seen" and "unknown" events and the 30-second gap

The dashboard's "Today" timeline should show when someone arrives, not one
entry per frame. `SEEN_GAP_SECONDS = 30` controls this:

- **Known person.** On every pass, the time the person was last seen is
  updated (`_last_seen`). A `seen` event ("Priya is in view") is added only if
  they had **not** been seen for more than 30 seconds. Someone who stays in
  view produces one event; someone who leaves for more than 30 seconds and
  comes back produces another. The same `_last_seen` time is reported as
  `last_seen` for each person in the API ("Last seen 2 min ago" on the People
  page).
- **Unknown face.** One shared timer is kept for all unknown faces. An
  `unknown` event ("Someone they don't know is in view") is added only if no
  unknown face had been seen for more than 30 seconds. Several unknown faces in
  the same frame produce one event.

These times are held in memory only and are lost when the program restarts.

### 7.4 How the wearer is introduced

For **every** recognised face on **every** pass, the loop calls
`announcer.seen(name, relationship)`. The announcer decides whether to speak:
it introduces a person the first time they are recognised, and again only
after they have been **out of view for 120 seconds**. Someone who stays in
view is introduced once. If speech cannot be heard yet (it is still loading, or
it is turned off), nothing is recorded, so the person is introduced as soon as
speech works. The wording ("This is Priya, your daughter.") and the timing are
described in [Speech and voice](speech-and-voice.md#3-introductions).

Unknown faces are never announced. They appear only as an orange "Unknown" box
on the camera picture and as "Someone they don't know" on the Live page, with a
link to add a person.

### 7.5 What the caregiver sees

The camera thread draws the latest recognition results on every frame before
encoding it for the dashboard stream (`Runtime._annotate`):

- known faces: a 3-pixel box in moss green (BGR `(79, 107, 47)`, which is the
  dashboard's `#2F6B4F`) with the name on a filled label above it;
- unknown faces: the same in marigold (BGR `(22, 138, 201)`, the dashboard's
  `#C98A16`) labelled "Unknown".

Labels use white OpenCV Hershey Simplex text at scale 0.7. The boxes come from
the most recent pass, so between passes they stay where the face was last
found. `GET /api/live` returns the same faces as data: name, relationship,
distance, and box.

---

## 8. Thread safety

Three locks protect recognition:

| Lock | Where | What it protects |
|---|---|---|
| `DeepFaceEmbedder._lock` (a plain `Lock`) | `faces.py` | **TensorFlow models are not safe to call from two threads at once.** Every call to `DeepFace.represent()`, and the one-time model load, happens while holding this lock. This matters because two threads can embed at the same time: the recognition thread (camera frames) and an HTTP request thread (a caregiver enrolling a photo). One waits for the other. |
| `Gallery._lock` (a re-entrant `RLock`) | `faces.py` | The folders and the cache. Creating, updating, and deleting people and photos, `refresh()`, and reading the cache all hold it. Enrolment holds it while it embeds the new photo, so a recognition pass that needs to refresh the cache waits until the enrolment finishes. |
| `Runtime._lock` | `runtime.py` | The latest frame, the latest faces, and the event list, shared between the camera, recognition, sign, and HTTP threads. |

The locks are always taken in the same order (gallery, then embedder), and the
recognition thread holds the embedder lock without the gallery lock while it
embeds a frame, so they cannot deadlock.

---

## 9. Configuration summary

| Option | Default | Effect |
|---|---|---|
| `--gallery` | `data/faces` | Folder of people. `signs.json` is stored in its parent folder. |
| `--threshold` | `0.30` | Cosine distance cutoff. |
| `--detector` | `opencv` | DeepFace detector backend. |
| `--interval` | `0.5` | Target seconds between recognition passes (`start` only). |

`cognisight identify photo.jpg` names the faces in a single photo from the
command line and prints each distance to three decimals, for example
`Priya (0.061)`; it exits with status 0 if anyone was recognised and 1
otherwise ("no face found" if there were no faces at all).

---

## 10. Limitations

- **Not tested on the Raspberry Pi.** The time per recognition pass on the Pi
  5 CPU is unknown. It will determine how quickly someone is introduced after
  they come into view.
- **Weak detector and alignment.** The OpenCV Haar detector finds mainly
  frontal, upright, well-lit faces. Its eye finder is a second Haar cascade,
  not a landmark model, so tilted faces are aligned poorly and may embed less
  consistently. Detectors with facial landmarks (such as YuNet or RetinaFace,
  both supported by DeepFace) were discussed as future work but have not been
  tried.
- **Cutoff not calibrated on real users.** 0.30 was chosen from a small number
  of test photos and DeepFace's own default. There is no per-person cutoff and
  no evaluation on a labelled set of the actual family members.
- **No liveness check.** A clear photo of an enrolled person held up to the
  camera would be recognised as that person.
- **Missed recognitions can cause a repeat introduction.** A person counts as
  "out of view" only by not being recognised. If someone stays in the room but
  is not recognised for 120 seconds (turned away, poorly lit, or outside the
  camera's view), they are introduced again when next recognised.
- **The largest face wins at enrolment.** If an uploaded photo shows several
  people, the largest face is stored as the person, which may be the wrong one.
- **Every face is embedded on every pass**, including faces of strangers.
  Nothing about an unknown face is stored, but it is processed.
- **Start-up failure is permanent until restart.** If DeepFace fails to load,
  the recognition thread stops and does not retry; the program must be
  restarted after the problem is fixed.
- **In-memory history.** "Last seen" times and the event timeline are lost on
  restart.
- **File-system case.** Person names are case-sensitive on Linux but the
  duplicate check is done by the operating system, so on a case-insensitive
  file system "priya" and "Priya" are the same person.
