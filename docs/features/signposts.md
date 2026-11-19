# Talking signposts (indoor guidance)

Talking signposts give the wearer indoor orientation and step-by-step guidance
using only the camera the device already has. A caregiver prints a sign for
each important place in the home (a camera-readable ArUco marker with the room
name in large letters) and tapes it beside the door. When the camera reads a
sign, the wearer hears "This is the kitchen." To guide them to a room, the
device plans a route through the signs and speaks one short, caregiver-written
direction at each sign, until the destination's sign is read and they hear
"You're at the bathroom."

The code is in `src/cognisight/signs.py` (the sign store, routes, the
navigator, and marker detection) and `src/cognisight/runtime.py` (the sign
detection thread and voice requests). The dashboard parts are
`web/src/Home.jsx`, `Sign.jsx`, `PrintSigns.jsx`, `PlanEditor.jsx`,
`Marker.jsx`, `markers.js`, `signs.js`, and the guide card in `Live.jsx`. Tests
are in `tests/test_signs.py` and `tests/test_server.py`.

> **Hardware status.** Signposts have not been tested on the Raspberry Pi or
> with the Pi camera. A guided trip was run through the real program on a
> development computer with a simulated camera showing the Hallway and then
> the Bathroom sign (recorded in [PROJECT_OVERVIEW.md](../PROJECT_OVERVIEW.md)).
> Reading distances in this document are calculations and desk measurements on
> synthetic images, not measurements with the Pi camera; the real reading
> distance must be measured on the Pi.

---

## 1. The problem, and the key insight

### 1.1 What the device cannot know

Turn-by-turn indoor guidance normally needs two things: where the person is
and which way they are facing. CogniSight's hardware provides neither
directly:

- The Raspberry Pi 5 has **no compass, gyroscope, or other motion sensor**, so
  it cannot tell which way the wearer is facing or when they turn.
- Satellite positioning does not work indoors, and the project has no GNSS
  receiver in any case (the available board was a 4G modem; see
  [location.md](location.md)).
- There are no beacons, depth cameras, or room scanners in the home.

An earlier version of indoor navigation let a caregiver type a map of rooms
and preview a route, but nothing sensed where the wearer actually was, so it
could not guide anyone.

### 1.2 Reading a sign means facing it

The camera is worn on the body and points the way the wearer is facing. A
small printed marker can only be read when it is in front of the camera,
reasonably close, and roughly facing it. So **at the moment the camera reads a
sign, the device knows two things at once**: the wearer is next to that sign,
and the wearer is facing it.

That makes directions simple and reliable. If the caregiver writes each
direction **for someone standing in front of the sign** ("Go out of this door
and turn left."), the words are always the right way round when they are
spoken, without any compass. Guidance is given one sign at a time, like
airport signage, rather than continuously.

The same mechanism addresses a common difficulty in dementia: not only finding
a room, but remembering what a room is for. Reading a sign can also play a
caregiver's reminder ("This is the kitchen. Tea is by the window.").

---

## 2. The markers

### 2.1 ArUco, dictionary 4×4_50

Each sign carries an **ArUco marker** from OpenCV's predefined dictionary
`DICT_4X4_50`:

- A marker is a square of 6 × 6 cells: a one-cell black border around a 4 × 4
  grid of black and white cells that encodes the marker's number.
- The dictionary has **50 markers, numbered 0 to 49** (`MARKER_COUNT = 50`), so
  a home can have at most 50 signs.
- The marker number *is* the sign's id in the sign store.

OpenCV's ArUco module is already part of the OpenCV package that DeepFace
installs (`opencv-contrib-python-headless`), so signs need no extra library or
hardware. A 4 × 4 code has fewer, larger cells than the 5 × 5, 6 × 6, and 7 × 7
ArUco dictionaries, so at a given printed size a low-resolution camera can
resolve it from further away; 50 codes are more than a home needs.

### 2.2 Detection

`MarkerDetector` (in `signs.py`) creates one
`cv2.aruco.ArucoDetector(DICT_4X4_50, DetectorParameters())` with OpenCV's
default detection parameters. For each frame it:

1. converts the BGR frame to greyscale;
2. calls `detectMarkers`, which returns the four corner points and the number
   of each marker found;
3. keeps a marker only if the **shortest of its four sides** is at least
   `MIN_MARKER_SIDE` pixels;
4. returns a list of `(id, [[x, y] × 4])`.

The detection thread then drops any marker whose number is not a saved sign
(section 8), so a stray marker from another project is ignored.

### 2.3 The minimum marker size: 24 pixels

`MIN_MARKER_SIDE = 24` pixels, at the camera's 640 × 480 resolution. A marker
smaller than that in the picture is too far away to act on: announcing a room
the wearer is several metres from would be confusing.

The size of a sign in the picture follows from the camera geometry. The Pi
Camera Module 2 has a horizontal field of view of 62.2°. At 640 pixels wide,
its focal length in pixels is

```
f = (640 / 2) / tan(62.2° / 2) ≈ 320 / 0.603 ≈ 530 pixels
```

A marker printed 14 cm wide (section 10), seen face-on from `d` metres, is
therefore about

```
width ≈ 530 × 0.14 / d ≈ 74 / d pixels
```

| Distance | Approximate marker width in the picture |
|---|---|
| 1.0 m | 74 px |
| 1.5 m | 49 px |
| 2.0 m | 37 px |
| 2.5 m | 30 px |
| 3.0 m | 25 px |
| 3.1 m | 24 px (the cut-off) |

So the 24-pixel cut-off by itself would allow signs up to about 3 m away. In
practice the limit is set by how small a marker OpenCV's detector can still
decode, and that depends strongly on how sharp the picture is:

- In desk tests on **synthetic** images, markers that had been blurred (by
  downscaling a larger marker image with area averaging, or by adding blur and
  noise) were decoded reliably from about **30 pixels** upwards, and became
  unreliable below that. 30 to 37 pixels corresponds to **about 2 to 2.5 m**
  for a 14 cm sign.
- Perfectly sharp synthetic markers decode at much smaller sizes (in a test
  with OpenCV 5.1.0, all 50 markers were still read at 14 pixels).

The working figure for a 14 cm sign is therefore **about 2 to 2.5 m under
realistic blur**. These are desk measurements on synthetic images, not
measurements on the Pi; how far the Pi camera reads a printed sign in real
lighting, with motion blur and focus, **must be measured**. The 24-pixel
cut-off is kept below the blurred-decoding limit, so in realistic conditions it
only removes markers the detector would barely see anyway, while still
ignoring signs that are clearly too far away (more than about 3 m) when the
picture happens to be sharp.

Because the cut-off uses the *shortest* side, a sign seen at an angle (which
looks narrower) has to be closer to be accepted than one seen face-on.

The automated test `test_printed_marker_is_read_and_far_ones_ignored` places a
120-pixel marker and an 18-pixel marker in a synthetic 640 × 480 frame and
checks that only the 120-pixel one is reported.

---

## 3. The sign store

### 3.1 Storage

All signs, directions, and the floor plan are kept in **one JSON file**,
`data/signs.json` (the file sits in the parent folder of the face gallery, so
`--gallery` moves it too). It is loaded once at start-up by `SignStore` and
rewritten after every change. Writes are atomic: the JSON is written to
`data/signs.tmp` and then renamed over `signs.json` with `os.replace`. A
re-entrant lock serialises access from the HTTP and detection threads.

### 3.2 Schema

```json
{
  "signs": [
    {"id": 0, "name": "Bedroom", "aliases": [], "note": "", "say_note": false},
    {"id": 1, "name": "Hallway", "aliases": ["corridor"], "note": "", "say_note": false},
    {"id": 2, "name": "Bathroom", "aliases": ["toilet", "washroom"], "note": "", "say_note": false},
    {"id": 3, "name": "Kitchen", "aliases": [], "note": "Tea is by the window.", "say_note": true}
  ],
  "links": [
    {"from": 0, "to": 1, "text": "Go out of this door and turn left."},
    {"from": 1, "to": 2, "text": "The bathroom is the second door on your right."},
    {"from": 1, "to": 3, "text": "The kitchen is straight ahead."},
    {"from": 1, "to": 0, "text": "Your bedroom is the first door on the left."},
    {"from": 3, "to": 1, "text": "Go back through this door."}
  ],
  "plan": {"width": 12.0, "height": 9.0, "walls": [], "doors": [], "labels": [], "signs": []}
}
```

| Field | Rule |
|---|---|
| `id` | The marker number, 0–49. A new sign gets the **lowest free number**. When all 50 are used, creating a sign fails with "All 50 printable signs are in use. Delete one first." (HTTP 409). |
| `name` | Whitespace collapsed; 1–40 characters ("Give the sign a name of up to 40 characters, such as Kitchen."). Must be unique, compared case-insensitively ("There is already a sign called Kitchen.", HTTP 409). |
| `aliases` | Other names the wearer might say, used only for voice requests. Accepts a list or a comma-separated string. Each is whitespace-collapsed and cut to 40 characters; duplicates (case-insensitive) are removed; at most 10 are kept. |
| `note` | A reminder, trimmed and cut to 300 characters. |
| `say_note` | Whether the note is spoken after "This is the kitchen." New signs created from the dashboard start with `false`; it is turned on with the checkbox "Say the note when they arrive" on the sign's page. |

When the file is loaded, entries without an `id` and `name` (signs) or without
`from`, `to`, and `text` (links) are dropped, and missing plan keys are filled
from the default plan (12 m × 9 m, empty). A missing or unreadable file starts
an empty store.

The API adds `last_seen` (the Unix time the camera last read the sign) to each
sign it returns. That time is held in memory by the navigator and is lost on
restart.

### 3.3 Deleting a sign

Deleting a sign removes it, **every link to or from it**, and its place on the
floor plan. The navigator then forgets it: its last-seen time is dropped, the
current room is cleared if it was that sign, and a trip to that sign is
cancelled. Because ids are reused (the lowest free number), a new sign can get
the deleted sign's number; the dashboard therefore asks the caregiver to take
the old printed sign off the wall when deleting ("Delete the Kitchen sign?
This can't be undone. Take the printed sign off the wall too.").

---

## 4. Links: one sentence for someone standing at the sign

A **link** is one step of directions from one sign to another:

```json
{"from": 1, "to": 2, "text": "The bathroom is the second door on your right."}
```

The sentence is written **for someone standing in front of the `from` sign,
facing it**, and it should get them to the `to` sign. It is spoken, word for
word, when the camera reads the `from` sign during a trip whose route goes to
`to` next.

Links are **directed**. A link from the Hallway to the Bathroom says nothing
about the way back; the way back needs its own sentence written at the
Bathroom sign, because "turn left" from one side is "turn right" from the
other.

### 4.1 Rules (`SignStore.set_links`)

The links leaving one sign are saved together. `PUT /api/signs/<id>/links`
replaces **all** directions leaving that sign with the list sent. For each
entry:

| Check | Error |
|---|---|
| Each entry is an object | "Each direction needs a sign and a sentence." |
| `to` is a number | "Choose which sign this direction leads to." |
| `to` is another existing sign (not itself) | "A direction must lead to another sign." |
| `text` is not empty after collapsing whitespace (cut to 240 characters) | "Write the direction as one sentence, such as “Turn left.”" |
| No two entries lead to the same sign | "There are two directions to the same sign." |

### 4.2 Editing links on the dashboard

On a sign's page, the section **"Ways from this sign"** lists one row per
destination, under the heading "With this sign in front of you…". Each row has
a "To" room selector and a "Directions" text box (placeholder: "The bathroom is
the second door on your right."). Below each row the page shows the reverse
direction, if one exists ("Coming back, at the Bathroom sign: “…”"), or "No way
back yet. Add one on the Bathroom sign." with a link, so the caregiver is
reminded that each direction is one-way. The page validates the rows before
saving ("Choose where each way goes.", "Write the directions for the way to the
bathroom.", "There are two ways to the bathroom. Keep one.").

---

## 5. The route graph and shortest path

The signs are the nodes and the links are the directed edges of a small graph.
`SignStore.route(start, goal)` finds the route with the **fewest signs** using
breadth-first search (BFS):

1. If `start == goal`, the route is `[start]`.
2. Build a neighbour list from the links, in the order they are stored.
3. Explore outward from `start` one link at a time, remembering how each sign
   was first reached.
4. When `goal` is reached, walk back through those records to produce the
   route, for example `[0, 1, 2]` (Bedroom → Hallway → Bathroom).
5. If the search runs out of signs without reaching `goal`, return `None` (no
   route).

BFS gives the route with the fewest steps, which is the number of directions
the wearer has to follow. The graph has no distances, so a route with fewer
signs is preferred even if it is physically longer. When two routes have the
same number of signs, the one found first (following the stored order of the
links) is used. With at most 50 signs the search is instantaneous.

The route is recalculated **from the sign the wearer is actually at** every
time a new sign is read during a trip (section 7), which is how wrong turns are
handled.

---

## 6. The Navigator: where the wearer is

`Navigator` (in `signs.py`) holds all guidance state and is driven by one
method, `sighting(sign_id)`, called for every saved sign in every processed
frame. It speaks through the announcer (so speech respects the dashboard's
speech switch and the queue) and adds events to the dashboard timeline. A
re-entrant lock protects its state, because sightings come from the detection
thread while trips are started and stopped from HTTP and voice threads.

### 6.1 State

| Field | Meaning |
|---|---|
| `room` | `{"id", "name", "since", "seen_at"}` for the **last sign read**, or `None`. `since` is when the wearer arrived at it; `seen_at` is the most recent sighting. |
| `guide` | The trip in progress (section 7), or `None`. |
| `last_seen` | Sign id → time of the last sighting (shown as "Last seen 2 min ago" on the Home page). |
| `_last_arrival` | Sign id → time the sign was last announced, or passed on a trip. |
| `_last_step` | Time the last guidance step was spoken. |

### 6.2 Room tracking

On every sighting:

- `last_seen[id]` is set to now.
- If the sign is **different** from the current room, the room changes:
  `room` becomes this sign with `since` and `seen_at` set to now, and a `room`
  event "In the kitchen" is added to the timeline (the Place page lists these
  as "Today's room changes").
- If it is the **same** sign, only `seen_at` (and the name, in case it was
  renamed) is updated.

The room is simply "the last sign read". It is not cleared when the wearer
walks away; instead, the dashboard shows how old it is. After
`ROOM_FRESH_SECONDS = 120` seconds without a sighting (in `web/src/signs.js`),
"In the hallway" becomes "Last seen in the hallway, 4 min ago".

### 6.3 Arrival announcements

If no trip is in progress (or the trip has already arrived), a sighting may
announce the room:

- The sign is announced when the wearer **arrives** at it: either it has never
  been announced, or it had **not been seen for at least
  `ARRIVAL_COOLDOWN = 120` seconds** before this sighting.
- And, in either case, it must not have been announced (or passed on a trip,
  section 7.7) in the last 120 seconds.
- And speech must be able to be heard (the Navigator's `can_speak`, which the
  runtime connects to the announcer's `can_speak()`: speech turned on and a
  working speaker loaded).
- All of this is kept **per sign**.
- The sentence is "This is {the room}." using the wording rule in `the()`:
  "Kitchen" becomes "the kitchen", "TV room" becomes "the TV room", and names
  beginning "the", "my", "your", or a possessive ("Priya's room") are kept as
  written.
- If the sign has a note and `say_note` is true, the note follows:
  "This is the kitchen. Tea is by the window."

Because detection runs several times a second, and every sighting updates the
sign's last-seen time, a wearer who stays in the kitchen and keeps seeing its
sign hears "This is the kitchen." **once**, however long they stay
(`test_staying_in_a_room_names_it_once` simulates ten minutes of sightings 30
seconds apart). A wearer who leaves and comes back within two minutes is not
told again (`test_walking_into_a_room_names_it_once`); one who comes back after
two minutes or more is.

While speech cannot be heard (still loading after start-up, or turned off),
nothing is announced and no announcement time is recorded
(`test_rooms_are_not_named_before_speech_works`). The sign's last-seen time is
still updated, though. So a sign that has never been announced is announced as
soon as speech works if it is still in view; a sign that was announced before
and is still in view when speech comes back is not announced again until the
wearer has been away from it for 120 seconds.

### 6.4 `RECENT_SECONDS`: when a sighting still counts as "here"

`RECENT_SECONDS = 120`. When a trip starts, the navigator needs to know where
the wearer is. It uses the current room only if that sign was seen within the
last 120 seconds; an older sighting is not trusted, because the wearer may have
walked anywhere since (`test_old_sighting_does_not_count_as_here` uses 300
seconds). The voice question "where am I?" uses its own, longer window of 300
seconds (see [speech-and-voice.md](speech-and-voice.md#62-where-am-i)).

---

## 7. Trips

### 7.1 Trip state

```json
{
  "destination": {"id": 2, "name": "Bathroom"},
  "route": [0, 1, 2],
  "visited": [0],
  "at": 0,
  "said": "Go out of this door and turn left.",
  "started": 1763539990.0,
  "arrived": 1763540030.0
}
```

`route` is the planned list of sign ids, `visited` the signs passed so far
(internal; not sent to the dashboard), `at` the last sign read on the way,
`said` the last sentence spoken for this trip, and `arrived` (present only once
the trip is finished) the time the destination was reached. The API returns
this object, without `visited`, as `guide` in `/api/home`, `/api/live`, and
`POST /api/guide`.

### 7.2 State machine

```
                 start(dest)                  destination sign read
   ┌──────────┐ ───────────────► ┌──────────┐ ─────────────────────► ┌─────────────┐
   │ No trip  │                  │ Guiding  │                        │ Arrived     │
   │          │ ◄─────────────── │          │                        │ (shown 20 s)│
   └──────────┘  stop(): voice   └──────────┘                        └─────────────┘
        ▲        "stop" or         │    ▲   any other sign read:            │
        │        dashboard         │    │   speak the next step,            │
        │                          └────┘   or "I don't know the way"       │
        └────────────────────────────────────────────────────────────────────┘
                     20 s after arrival (cleared when the state is next read),
                     or stop(), or the destination sign is deleted
```

Starting a new trip while one is in progress simply replaces it.

### 7.3 Starting a trip

A trip starts when the caregiver chooses a room under **"Guide them to…"** on
the Live page and presses **Start guiding** (`POST /api/guide`), or when the
wearer asks by voice ("take me to the bathroom"). `Navigator.start(dest)`:

1. records a `guide` event "Guiding to the bathroom";
2. checks whether the wearer's current room was seen within `RECENT_SECONDS`
   (120 s);
3. **if it was**, immediately takes the first step from that sign (section
   7.4), so the wearer hears the first direction at once (or "You're at the
   bathroom." if they are already there);
4. **if it was not**, says "Let's go to the bathroom. Look around for a sign on
   the wall." The trip then waits for the first sign to be read, and `at` and
   `route` stay empty until then.

An unknown destination returns HTTP 404 "Choose a sign to guide them to.".

### 7.4 Each step

When a sign is read during a trip that has not yet arrived, the normal arrival
announcement is **not** made; instead `_guide_step` runs:

1. **Destination reached.** If the sign is the destination, the device says
   "You're at the bathroom.", adds the event "Arrived at the bathroom", marks
   the trip `arrived`, and sets `at` to the destination. The arrival also
   counts as the destination's announcement (section 6.3), so "This is the
   bathroom." does not follow straight after.
2. **Still at the same sign.** If the sign is the one the last step was spoken
   at and fewer than `STEP_REPEAT = 30` seconds have passed, nothing happens.
   Detection reads the sign several times a second, so this is what prevents
   repetition.
3. **Repeat after 30 seconds.** If the wearer is still in front of the same
   sign 30 seconds or more after the step was spoken, the step is spoken
   again. A wearer who lingers, perhaps unsure, hears the direction every 30
   seconds while the sign stays in view.
4. **A new sign.** The navigator:
   - records the sign as passed (its announcement time is set; see 7.7);
   - adds it to the end of `visited`, or, if the wearer has come back to a
     sign already in `visited`, cuts `visited` back to end at that sign, which
     forgets the detour made after it (7.5);
   - computes the shortest route **from this sign** to the destination;
   - if a route exists, speaks the link text from this sign to the next sign
     on the route, sets `route` to the signs already passed followed by the new
     route, and adds the event "At the hallway: “The bathroom is the second
     door on your right.”";
   - if no route exists, says "I don't know the way to the bathroom from
     here." and adds the event "No directions from the kitchen to the
     bathroom". The trip stays active, so reading a sign from which a route
     does exist resumes guidance.

### 7.5 Wrong turns and re-routing

Because the route is recomputed from whichever sign is read, a wrong turn needs
no special handling. If the wearer heading for the bathroom walks into the
kitchen instead, the Kitchen sign is read, the shortest route from the kitchen
(Kitchen → Hallway → Bathroom) is planned, and they hear the kitchen's way back
to the hallway, "Go back through this door." (`test_wrong_turn_is_rerouted`.)

The `route` list shown on the dashboard is built as "signs already passed, then
the new shortest route". When the wearer returns to a sign they had already
passed, the passed list is cut back to that sign, so the detour disappears and
no sign appears twice. For example, on a trip to the bathroom that goes Bedroom
→ Hallway → Kitchen → Hallway, the route shown is Bedroom, Hallway, Kitchen,
Hallway, Bathroom while the wearer is in the kitchen (the detour and the way
back), and Bedroom, Hallway, Bathroom again once they are back in the hallway
(`test_going_back_past_a_sign_does_not_repeat_it_in_the_route`).

### 7.6 Arrival kept visible for 20 seconds

After arrival, the trip is kept for `ARRIVED_SHOWN = 20` seconds so the
caregiver's dashboard can show "They've reached the bathroom." with every step
ticked off. The trip is removed the first time the state is read after those
20 seconds (the dashboard polls it every second on the Live page). While the
trip is in its arrived state, further sightings give no more directions; they
are treated as ordinary sightings under the normal announcement rules of
section 6.3.

### 7.7 Why signs passed on a trip are not re-announced

When a sign is passed during a trip, its announcement time is set as if it had
been announced, so the rules of section 6.3 treat it as recently announced. The code comment states the reason: "A sign passed on a trip
has had its say; don't name it again on the way back." Without this, a wearer
who reaches the bathroom and walks back past the hallway sign within two
minutes would hear "This is the hallway." immediately after being guided
through it, which adds words without adding information. The test
`test_guided_trip_one_step_per_sign` checks that reading the Hallway sign just
after arrival says nothing new.

### 7.8 Stopping a trip

A trip ends early when the caregiver presses **Stop guiding** (`DELETE
/api/guide`, event "Stopped guiding from the dashboard"), when the wearer says
"stop" (event "Stopped guiding when asked"), or when the destination sign is
deleted.

---

## 8. The detection thread

Sign detection runs in its own thread, `_sign_loop`, **independently of face
recognition**. Both threads read the newest camera frame from the same shared
slot (see [ARCHITECTURE.md](../ARCHITECTURE.md)), but neither waits for the
other. Marker detection is much cheaper than face recognition, so signs are
read even when a recognition pass is slow, and guidance keeps working if
DeepFace fails to load.

Each pass:

1. Wait for a frame newer than the last one processed (up to 2 seconds).
2. Detect markers (section 2.2). If detection raises, the error "Reading signs
   failed: …" is recorded and the frame counts as having no signs. The error is
   cleared again by the next successful detection, so `signs.ok` in
   `/api/status` recovers by itself.
3. Keep only markers whose number is a saved sign, and attach the sign's name.
4. Publish them (for the camera picture and `markers` in `/api/live`).
5. Call `navigator.seen(ids)`, which calls `sighting()` for each.
6. Wait `SIGN_INTERVAL = 0.25` seconds.

So signs are processed at most about four times a second.

If OpenCV's ArUco module is not available when the thread starts, it records
"Signs need OpenCV with the ArUco module: …" (shown on the timeline and in
`/api/status`) and stops; the rest of the device keeps running.

---

## 9. What the caregiver sees

### 9.1 On the camera picture

The camera thread outlines every saved sign in view with a 3-pixel line in the
dashboard's route blue (BGR `(138, 95, 47)`, which is `#2F5F8A`), joining its
four detected corners, and writes the sign's name in white on a filled blue
label just below the marker. Faces are drawn in moss green (known) and
marigold (unknown); see [face-recognition.md](face-recognition.md#75-what-the-caregiver-sees).

### 9.2 On the dashboard

| Where | What |
|---|---|
| Live page, over the camera picture | A chip "Sign in view: Hallway" (or "Signs in view: …"). |
| Live page, "With them now" | "In the hallway" or, after 120 s, "Last seen in the hallway, 4 min ago". |
| Live page, guide card | "Guide them to…" selector and **Start guiding**, shown when there are at least two signs. During a trip: "Guiding them to the bathroom", the route as a list of steps (signs up to and including the last one read are "reached", the next one is "next"), "They've reached the bathroom." on arrival, "Last said: “…”", "Started 1 min ago", and **Stop guiding**. |
| Live page timeline | `room` events with a blue diamond marker; `guide` events with a blue ring marker. |
| Home page | The floor plan, and the list of signs, each with a small marker, "In view now" / "Last seen …" / "Not seen yet", and "2 ways out" / "No ways out yet". The sign the wearer is at is highlighted. |
| Place page, "At home" | "In the kitchen since 2:14 pm" and up to 8 of today's room changes. |

The guidance colour on the dashboard is the `--route` token, `#2F5F8A` in the
light theme (`#8AB8E6` in the dark theme). The light-theme value is exactly the
blue drawn around signs on the camera picture, so signs and guidance share one
colour everywhere.

---

## 10. The printed sign

### 10.1 Format

The **Print signs** page (`/home/print`, or `/home/print?ids=3` for one sign)
lays out one sign per A4 sheet. When printed (CSS `@page { size: A4; margin:
0 }`):

| Part | Size |
|---|---|
| Sheet | 210 × 296 mm, padding 22 mm at the top, 11.67 mm at the sides, 14 mm at the bottom |
| Marker image | 186.67 mm square, which is the 6 × 6-cell marker plus a one-cell white margin on every side (8 cells in all) |
| Marker itself (black border included) | **140 mm (14 cm)** across; each cell is 23.33 mm |
| White margin ("quiet zone") | One cell, 23.33 mm, on every side, so the camera can find the marker's edge |
| Room name | Bold, below the marker: 30 mm high for names of up to 9 characters, 22 mm for up to 16, 16 mm for longer names |
| Footer | "CogniSight sign 3. Keep this at eye level beside the door." in 12 pt |

The page tells the caregiver to print "at 100% size, not “fit to page”, so each
marker comes out about 14 cm across", to use plain white paper, and to avoid
glossy lamination, which can glare. Colours are printed exactly
(`print-color-adjust: exact`). The dashboard, navigation, and instructions are
hidden when printing. On screen, each sheet is shown as a scaled preview with
the same proportions.

### 10.2 Reproducing the exact marker bits in the browser

The dashboard draws markers itself rather than asking the device for images.
`web/src/markers.js` contains `MARKER_BITS`, an array of 50 strings of 16
characters, one per marker number, exported from OpenCV's `DICT_4X4_50`. Each
string is the 4 × 4 inner grid read row by row, where `"1"` is a white cell and
`"0"` a black cell. For example, marker 0 is `"1011010100110010"`.

`Marker.jsx` turns a string into an SVG:

1. a white background square covering the marker plus its quiet zone (`quiet`
   cells, 1 by default; the floor plan uses 0.6);
2. a 6 × 6 black square;
3. a 1 × 1 white square at cell (1 + column, 1 + row) for every `"1"` bit.

The SVG uses `shape-rendering="crispEdges"`, so cell edges are not blurred, and
it scales to any size without loss, which is why the printed marker is sharp at
14 cm. The same component draws the small markers in the sign list (52 px),
on a sign's page (88 px and 200 px), and on the floor plan.

All 50 strings were checked against the markers produced by OpenCV 5.1.0's
`cv2.aruco.generateImageMarker` for `DICT_4X4_50`: the inner bits match for
every marker, and every generated marker has the full black border the SVG
draws.

---

## 11. The floor plan editor

The floor plan is **optional and for the caregiver only**. Guidance uses the
signs and the links between them; it never uses the plan's geometry. The plan
helps the caregiver decide where signs should go and shows the route map and
the wearer's position at a glance. It is on the Home page
(`web/src/PlanEditor.jsx`).

### 11.1 Coordinates

The plan is in metres, with the origin at the top-left, x pointing right and y
pointing down. Angles are in degrees, with 0 pointing right ("east" on the
drawing) and 90 pointing down. The default plan is 12 m × 9 m. Positions snap
to a 0.5 m grid (`GRID`), with major grid lines every 1 m.

### 11.2 Tools

| Tool | How it works |
|---|---|
| **Select** | Tap an item to select it, then drag to move it. Dragging empty space moves the view. A selected wall shows a handle at each end for changing its length and direction. |
| **Wall** | Press and drag. Ends snap to the 0.5 m grid; holding Shift restricts the wall to 45° steps with its length snapped to the grid. Walls shorter than 0.25 m (`MIN_WALL`) are ignored. The length is shown while drawing and after ("Wall added, 3.5 m long."). |
| **Door** | Tap on or near a wall (within 0.75 m, or 24 screen pixels when zoomed out). A 0.9 m door is placed in the wall, centred where tapped (in 5 cm steps), kept inside the wall, and aligned with it. It is drawn as a gap with a swing arc and leaf. A selected door can be given a width of 0.7, 0.8, 0.9, 1.0, or 1.2 m and rotated by 90°. |
| **Room name** | Tap inside a room. A label "Room" appears and the text box is focused so the caregiver can type the name (up to 40 characters). |
| **Place sign** | Choose a sign from "Sign to place" (signs already placed are marked "(on the plan)"), then tap beside the wall where it will hang. If the tap is within 1.5 m of a wall (or 24 screen pixels), the sign is put against the wall, 0.08 m (`SIGN_OFFSET`) off it on the tapped side, **facing away from the wall into the room**. Otherwise it is placed on the grid facing down (90°). Placing a sign that is already on the plan moves it. After placing, the next sign not yet on the plan is chosen automatically. A selected sign can be rotated in 45° steps, opened ("Open sign"), or taken off the plan. After a new sign is added on the Home page, the editor switches to this tool with that sign chosen. |
| **Pan** | Drag to move the view. |

Other controls: **Undo** (up to 100 steps, also Ctrl/Cmd + Z), **Zoom in**
(×1.25), **Zoom out** (×0.8), **Fit** (show the whole plan), a scale bar
(0.5, 1, 2, 5, 10, or 20 m, whichever is at least 56 pixels long), and width and
height boxes (2–50 m, in 0.5 m steps). On touch screens, two fingers move and
zoom the plan; on a trackpad, pinching (Ctrl + wheel) zooms; a plain mouse
wheel scrolls the page. On the keyboard, with the plan focused: the arrow keys
move the selected item by 0.5 m (0.1 m with Shift) or move the view by 1 m when
nothing is selected; Delete or Backspace removes the selected item; R rotates
it; Escape cancels; + and − zoom. A screen-reader summary describes the plan
("12 m by 9 m plan, 14 walls, 5 doors, 4 room names, 4 signs.").

Limits match the server: 400 walls, 100 doors, 60 room names; reaching one
shows a message such as "The plan already has 400 walls, the most it can hold."

Changes are local until **Save plan** is pressed. "Changes not saved yet." is
shown meanwhile, and leaving the page (inside the dashboard or by closing the
tab) asks for confirmation. While there are unsaved changes, updates from the
device do not overwrite the drawing; when there are none, the editor takes in
the device's latest plan (for example, after a sign is deleted elsewhere).

### 11.3 The reading-zone wedge

Every placed sign is drawn with a shaded **wedge** in front of it: a sector of
a circle centred on the sign, opening in the direction the sign faces, with a
total angle of `ZONE_ANGLE = 70°` (35° either side of the facing direction) and
a radius of `ZONE_LENGTH = 2.5` m. It is drawn in moss green at 12 % opacity
with a dashed outline, underneath everything else.

The wedge exists so the caregiver can see **where the wearer has to stand for
the camera to read the sign**, and check that someone walking up to a door will
actually pass through that area. A sign hung behind an open door, facing a
wall, or at the far end of a long room shows a wedge that the walking route
does not cross. The 2.5 m radius is the upper end of the estimated reading
distance of a 14 cm sign (about 2 to 2.5 m under realistic blur; section 2.3),
so the real reading area may be smaller. The 70° angle is described in the code as how wide
an angle the camera can read a sign from; it has not been measured.

The wedge is an approximation. It is not clipped by walls, and it has the same
radius at its edges as in the middle, whereas a sign seen 35° off-centre looks
about cos 35° ≈ 82 % as wide and so, by the geometry in section 2.3, can only be
read from about 82 % as far.

### 11.4 How links are drawn

Links are created on each sign's page (section 4.2), not drawn on the plan. The
plan **displays** them as arrows between every pair of linked signs that are
both placed:

- Each arrow is a curve from one sign to the other, starting and ending just
  outside the sign icons, bent to the left of the direction of travel by 16 %
  of its length, so the two one-way directions between a pair of signs appear
  as two separate curves instead of lying on top of each other.
- Normal links are thin grey arrows at 55 % opacity.
- During a trip, links between consecutive signs of the planned route are drawn
  thicker (3.5 px) in the guidance blue, on top of the others.
- Signs closer together than the size of their icons get no arrow.

Signs on the plan are drawn as small markers with a halo and their name. A sign
currently in view gets a green halo; the sign of the wearer's current room gets
a pulsing blue ring (the animation stops when the browser asks for reduced
motion).

### 11.5 Plan schema

```json
{
  "width": 12, "height": 9,
  "walls":  [{"x1": 0, "y1": 0, "x2": 12, "y2": 0}],
  "doors":  [{"x": 3, "y": 0, "angle": 0, "width": 0.9}],
  "labels": [{"x": 2, "y": 2, "text": "Kitchen"}],
  "signs":  [{"sign": 3, "x": 4.5, "y": 0.1, "facing": 90}]
}
```

`doors.angle` is the direction of the wall the door sits in. `signs.facing` is
the direction the printed side faces, which is where someone must stand to read
it.

### 11.6 Server-side cleaning and clamping

`PUT /api/plan` never stores what it is sent as-is. `SignStore.set_plan()`
rebuilds the plan from scratch:

| Part | Cleaning |
|---|---|
| Whole body | Must be a JSON object, or the request fails with "That is not a floor plan." (HTTP 400). |
| `width`, `height` | Converted to numbers and clamped to 2–50 m. Missing or invalid values become 12 and 9. |
| Lists | `walls`, `doors`, `labels`, `signs` must each be a list if present ("The plan's walls must be a list."), and may hold at most 400 walls, 100 doors, 60 labels, and 50 signs ("A plan can hold at most 400 walls."). Entries that are not objects are dropped. |
| Coordinates | Every x is clamped to 0–width and every y to 0–height. Values that are not numbers, or are NaN or infinite, become 0. |
| Angles | Taken modulo 360, so −90 becomes 270 and 450 becomes 90. |
| Door width | Clamped to 0.5–3 m; default 0.9. |
| Labels | Whitespace collapsed, cut to 40 characters; labels with empty text are dropped. |
| Signs | `sign` must be the id of an existing sign; others are dropped. A sign listed twice keeps its last position. |
| Precision | All numbers are rounded to 3 decimal places. |

The cleaned plan is saved and returned, and the editor replaces its copy with
it. The dashboard applies a similar normalisation to whatever it receives
(`normalizePlan()` in `web/src/signs.js`), additionally dropping zero-length
walls and defaulting a sign's facing to 90°.

---

## 12. Worked example: Bedroom → Hallway → Bathroom

This uses the house from the tests (`tests/test_signs.py`): signs Bedroom (0),
Hallway (1), Bathroom (2, aliases "toilet" and "washroom"), and Kitchen (3,
note "Tea is by the window.", spoken on arrival), with the five links shown in
section 3.2. Times are seconds from the start.

| Time | What happens | Wearer hears | Timeline | Trip state |
|---|---|---|---|---|
| 0 | The wearer is in front of the Bedroom sign. | "This is the bedroom." | "In the bedroom" | No trip |
| 10 | The caregiver chooses **Bathroom** and presses **Start guiding**. The Bedroom sign was seen 10 s ago (within 120 s), so the first step is taken at once. Route from Bedroom: 0 → 1 → 2. | "Go out of this door and turn left." | "Guiding to the bathroom"; "At the bedroom: “Go out of this door and turn left.”" | route [0, 1, 2], at 0 |
| 10–40 | The Bedroom sign stays in view. | Nothing (fewer than 30 s since the step) | — | — |
| 25 | The wearer reaches the Hallway sign. The room changes; no "This is the hallway." because a trip is in progress. Route from Hallway: 1 → 2. | "The bathroom is the second door on your right." | "In the hallway"; "At the hallway: “The bathroom is …”" | route [0, 1, 2], at 1 |
| 40 | The Bathroom sign is read. | "You're at the bathroom." | "In the bathroom"; "Arrived at the bathroom" | at 2, arrived |
| 40–60 | The dashboard shows all steps ticked and "They've reached the bathroom." | — | — | arrived |
| 50 | Walking back, the wearer reads the Hallway sign again. It was passed on the trip 25 s ago, so it counts as recently announced and the wearer has not been away from it for 120 s. | Nothing | "In the hallway" | arrived |
| > 60 | The next time the dashboard reads the state, the trip is cleared. | — | — | No trip |

**With a wrong turn.** Suppose that at time 30, after hearing the hallway
direction, the wearer walks into the kitchen instead. The Kitchen sign is read;
the shortest route from the kitchen is Kitchen → Hallway → Bathroom; the wearer
hears the kitchen's link to the hallway, "Go back through this door." (not
"This is the kitchen. Tea is by the window.", because a trip is in progress).
When they reach the Hallway sign again, they hear "The bathroom is the second
door on your right." once more, and the trip continues as before.

**With the trip started by voice.** The wearer says "I need the toilet". The
phrase matches the "go" command ("need the"), and "toilet" is an alias of the
Bathroom sign, so the same trip starts. If no sign had been read in the last
120 seconds, they would first hear "Let's go to the bathroom. Look around for a
sign on the wall."

---

## 13. Limitations

- **Untested on the Pi.** Real reading distance and angle with the Pi camera,
  in home lighting and while the wearer walks, are unknown. The "about 2 to
  2.5 m" figure is a calculation backed by desk tests on synthetic images, and
  sharp images decode much smaller markers, so the real limit must be measured
  on the Pi camera.
- **Guidance happens only at signs.** Between signs the device is silent and
  knows nothing about the wearer's movement. Signs belong where a decision is
  needed: doorways and where a hall splits. An inertial sensor to follow turns
  between signs is listed as future work.
- **The wearer must face the sign.** A sign behind the wearer, or one they walk
  past without looking at, is not read.
- **Directions are only as good as the caregiver's sentences**, and they are
  one-way: each way back has to be written separately.
- **Fewest signs, not shortest distance.** The route graph has no distances.
- **At most 50 signs**, and ids are reused after deletion, so an old printed
  sign left on the wall would be read as the new sign with its number.
- **No route means no help.** At a sign with no written route to the
  destination, the wearer hears only "I don't know the way to … from here."
- **The room is the last sign read.** It does not change until another sign is
  read, so it can be out of date; the dashboard shows its age instead.
- **"Away" means "sign not read".** A wearer who stays in a room but does not
  face its sign for two minutes hears "This is the kitchen." again the next
  time they read it.
- **Steps are not held back while speech is off.** Room announcements wait
  until speech can be heard, but guidance steps during a trip are still taken
  (and shown on the dashboard as "Last said") even when speech is turned off,
  so the wearer would not hear them.
- **The floor plan is not used for guidance** and its wedge is an approximate
  aid, not a measured reading area.
