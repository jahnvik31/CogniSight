# Design decisions and project history

This document records how CogniSight reached its current form: what was
originally proposed, what the available hardware could actually do, which
alternatives were considered at each decision, and why the current choice was
made. It is written as source material for the project report. Facts that
were measured are labelled as measurements; estimates are labelled as
estimates.

## 1. The original proposal

The project set out to build an offline aid for a person living with dementia
with four features, in this priority order:

1. Contextual facial recognition: tell the wearer who is in front of them.
2. Outdoor navigation: help the wearer, or a caregiver, know where they are
   outside the home.
3. Indoor navigation: help the wearer find their way between rooms.
4. A caregiver dashboard: let family members set up the device and check on it.

The team split the work: Meghana on facial recognition and contextual
information, Sharanya on outdoor navigation, Jahnvi on the caregiver interface
and integration, and Jahnvi with Archisha on indoor navigation.

The first software version followed that plan on paper. It had a face
pipeline (YuNet for detection, SFace for matching), a client for a satellite
positioning daemon, a room map typed in by the caregiver with a shortest-path
preview, and a four-panel caregiver page. About 190 automated tests protected
that design. It was never shown running on the Raspberry Pi, and several parts
did not match the hardware the team actually had.

## 2. What the hardware could and could not do

| Part | What it is | Consequence |
|---|---|---|
| Raspberry Pi 5, 8 GB | Quad-core Arm Cortex-A76 at 2.4 GHz, no GPU used for inference | Face recognition and speech must run on the CPU. There is no compass, gyroscope, or GPS on the board. |
| Raspberry Pi Camera Module 2 | Sony IMX219 sensor, 62.2° × 48.8° field of view, connected with a 22-pin cable | Confirmed working on the Pi with a Picamera2 streaming script. This is the only sensor the device has for its surroundings. |
| ADIY SIM A7670C board | A 4G LTE modem with RS232 and a 1.8 V serial header | It is a cellular modem, not a satellite receiver. A GNSS fix on this chip family needs a separate GNSS antenna, and some variants of the A7670C do not include GNSS at all. No SIM card was bought with it. |
| AUX wired headset | 3.5 mm jack | The Raspberry Pi 5 has no headphone jack, so the headset cannot be plugged in directly. Speech goes to Bluetooth earphones paired with the Pi instead. |

These facts drove most of the later decisions. Any feature has to work with
one forward-facing camera, a CPU, a speaker output, and an optional
microphone.

## 3. Face recognition

### 3.1 Replacing YuNet and SFace with DeepFace

The first pipeline used two small OpenCV models: YuNet to find faces and SFace
to compare them. It stored no photos, only signatures, and required three
consecutive matches before saying a name. It had not been shown working on the
Pi.

It was replaced with DeepFace using the Facenet512 model. The reasons:

- A team member had already seen DeepFace with Facenet512 running on a
  Raspberry Pi 5. That is direct evidence that this stack can work on the
  target hardware, which the earlier pair lacked.
- A reference project, VISU-X, used the same library and settings, so there
  was a working configuration to start from.
- Facenet512 produces a 512-number signature (embedding) per face, which
  separates different people well with a simple cosine-distance comparison.
- One library covers face detection, alignment, and embedding.

### 3.2 The 0.30 cutoff

DeepFace compares two faces by the cosine distance between their embeddings:
0 means identical direction, larger means less similar. VISU-X accepted a
match at a distance of 0.70 or less.

During testing, that cutoff was too loose. Two photos of people who were not
in the gallery were matched to someone who was, at distances of 0.285 and
0.339. Enrolled photos of the team members matched at a distance of 0.0. A
cutoff of 0.30 rejects both false matches and still accepts the true ones.
CogniSight uses 0.30.

The choice deliberately favours silence over a wrong name. For a person with
dementia, being told that a stranger is their daughter is worse than hearing
nothing. The cutoff can be changed with `--threshold`.

On a laptop webcam, a person enrolled from the live camera was later
recognised at a distance of about 0.06, well inside the cutoff.

### 3.3 Several photos per person, best match wins

Each person is a folder of photos. A face in the camera is compared with every
photo of every person, and each person's score is their **best** (smallest)
distance. The alternative, averaging over a person's photos, would punish a
person for having one photo from an unusual angle. Taking the best match means
that adding photos from different angles only ever makes recognition more
likely, which gives the caregiver a simple rule: "add 3 to 5 photos from
slightly different angles."

### 3.4 Speaking immediately instead of three in a row

The first design waited for three consecutive matches. To the wearer that felt
like hesitation. With a strict cutoff, a single strong match is already
reliable, so CogniSight now speaks on the first match. To avoid the opposite
problem, repeating the same introduction every second, a person is introduced
again only after they have been out of view for two minutes. Someone who
stays in the room is introduced once, however long they stay. If speech is
off or still loading when someone is recognised, nothing is recorded, so they
are introduced as soon as speech works. The aim is fewer, calmer
introductions.

### 3.5 Keeping the OpenCV face detector

DeepFace offers several face detectors: OpenCV, YuNet, RetinaFace, MTCNN, SSD,
MediaPipe and YOLO variants. The detector finds the face box. Some detectors
also find eye positions, which DeepFace uses to rotate the face upright
(alignment) before embedding it.

The OpenCV detector was kept because it is the configuration that was
actually tested and that produced the 0.30 results above. Its eye finder is
weak, so tilted faces are aligned less well. YuNet and RetinaFace give real
facial landmarks and would improve alignment. YuNet has a known issue in
DeepFace where eye points can stay in a resized coordinate frame. RetinaFace
is slower. Switching is a one-flag change (`--detector`) and is listed as
future work, to be tested on the Pi before adopting it.

The OpenCV detector occasionally reported a small false face overlapping a
real one (seen on a pillow beside a face during testing). CogniSight drops any
detection that overlaps a larger face by more than 15% of its own area.

## 4. Speech

### 4.1 Choosing the speech library

The device needs to speak (text-to-speech) and, optionally, to listen for a
few commands (speech-to-text), offline, on the Pi's CPU. Options considered
in November 2026:

| Option | Strengths | Weaknesses |
|---|---|---|
| Piper | Very fast on a Pi 5 (reported real-time factor about 0.12–0.14) | The original project was archived in October 2025 and no longer receives updates |
| Kokoro (82M parameters) | The most natural voice of the small models | Heavier; reported around 0.4–0.5 real-time factor on a Pi 5 with an optimised runtime |
| KittenTTS | The smallest neural English voice (15–80M parameters) | English only, small voice set |
| Moonshine (speech-to-text) | Streaming models built for edge devices; the tiny model (about 34M parameters) is reported at about 240 ms per phrase on a Pi 5 | Speech-to-text only on its own |
| espeak-ng | Tiny, installed from the operating system | Robotic voice |

The choice was **moonshine-voice**, one MIT-licensed library that bundles
Moonshine streaming speech-to-text with Kokoro and Piper voices, ships
prebuilt packages for 64-bit Arm Linux, and handles audio playback. Using one
library for both directions keeps the install simple. The default voice is
Kokoro "af_heart". espeak-ng is installed as a fallback, so the device can
still speak if the neural voice fails to load.

Measured on a Windows laptop (not on the Pi): the first load took 54.5
seconds, including downloading about 80 MB of voice files. After that the
sentence "This is Priya, your daughter." took 3.3 seconds from request to the
end of playback. Speed on the Pi has not been measured.

### 4.2 Bluetooth earphones

The Pi 5 has no headphone jack and the team's headset is wired. Speech
therefore plays on the Pi's default audio output, and the wearer uses
Bluetooth earphones paired from the Pi desktop. Microphones on Bluetooth
earphones switch the connection to a low-quality telephone mode on Linux and
are unreliable, so a USB microphone is recommended for voice commands.

### 4.3 No wake word

The device listens continuously and reacts only to a short list of phrases.
A wake word ("Computer, …", as in the first design) was dropped to keep
interaction simple for the wearer. The trade-off is that the word "stop" said
in ordinary conversation also stops speech. For a demonstration this is
acceptable; for real use a wake word or a physical button would be safer.

### 4.4 Queued speech

Speech is queued rather than interrupting itself, so a direction never cuts
off an introduction. Only "stop" (or the dashboard switch) interrupts. While
the device is speaking, anything the microphone hears other than "stop" is
ignored, so over a loudspeaker the device cannot react to its own sentences
(for example "Let's go to the bathroom").

## 5. Outdoor location

### 5.1 Why satellite positioning was dropped

The A7670C board is a cellular modem. A satellite fix needs a GNSS antenna
that was not available, and it is not certain that this variant of the chip
includes GNSS at all. Without a fix, outdoor navigation (walking directions)
was not possible, and it was dropped.

### 5.2 Alternatives considered

| Option | Why it was not used |
|---|---|
| OpenHaystack (Apple Find My network) | A small Bluetooth beacon is located by passing iPhones. Retrieving the reports needs a Mac with an Apple ID and depends on iPhones passing nearby. Too complex for the deadline. |
| Mozilla Location Service | Closed to outside users in June 2024 |
| OpenCelliD | Needs the IDs of nearby cell towers, which the Pi cannot see without a working modem and SIM. Indian coordinates are rounded to about 1 km. |
| IP address lookup | Places the college's shared internet connection, kilometres from the device |
| Google Geolocation API | Can place a device to tens of metres from nearby Wi-Fi. Needs a billing account (see below). |

### 5.3 Google Geolocation and billing

Google's Geolocation API needs a billing account even for its free allowance.
For an Indian account, an identity check with PAN or Aadhaar must be completed
within 30 days. A UPI prepayment of ₹500 to ₹1,000 does not complete that
check. Creating a separate billing account was blocked because the Google
account belongs to an organisation and lacked permission there. An existing
trial billing account was linked to unrelated projects outside the
organisation, and enabling the API looped back to the billing page. An API key
was eventually obtained.

### 5.4 The two-access-point rule and honest labelling

Google only uses Wi-Fi when the request lists at least two access points.
"Access point" here means a radio identified by its hardware address (BSSID),
not a network. One dual-band router usually counts as two, and neighbours'
routers count even if the device is not connected to them. With fewer than
two, Google falls back to the internet address.

In the hostel, Windows saw only one access point. The result was the internet
address estimate: 16.49549, 80.50980, with an accuracy radius of about 2.7 km,
which is the Vijayawada and Amaravati area, not the room.

CogniSight therefore scans every access point the Pi can hear (`nmcli`) and
labels each result honestly. If two or more access points were sent and the
answer is within 1,000 m, it is shown as a Wi-Fi fix with its radius.
Otherwise it is shown as "only the internet connection's location", with the
width of the area. The dashboard never presents a rough area as the room.

## 6. Indoor navigation: from a typed map to talking signposts

### 6.1 What was wrong with the first design

The first indoor feature let the caregiver type rooms and doorways and preview
a shortest path from a room they clicked. Nothing sensed where the wearer
actually was: no beacons, no depth camera, no floor plan. It was a map for the
caregiver, not help for the wearer. Over time the practical substitute became
"stream the camera to the dashboard so the caregiver can see where they are",
which is surveillance rather than support.

### 6.2 The team's idea: room markers read by the camera

The indoor-navigation owners proposed printed codes (QR codes) in each room,
read automatically by the camera, to tell the wearer where they are and help
them navigate.

### 6.3 The orientation problem

Directions such as "turn left" only make sense if the device knows which way
the wearer is facing. The Raspberry Pi has no compass or gyroscope. Adding a
motion sensor (IMU) was possible, but magnetometers are unreliable indoors and
the deadline was short.

The key observation: **when the camera reads a sign, the wearer is facing that
sign.** The camera is worn facing forward, so a sign in view tells the device
both where the wearer is and which way they face, at that moment. A direction
written "for someone standing in front of this sign" is therefore always the
right way round when it is spoken. No compass is needed.

The cost is that guidance happens at signs, not between them. That matches
how people use signage in airports and hospitals: a sign at each decision
point. Signs belong at doorways and where a corridor splits.

### 6.4 ArUco markers instead of QR codes

QR codes carry text but need to be close and fairly straight-on to decode.
ArUco markers are square black-and-white patterns designed for cameras. They
decode at an angle and from further away, they are found in a few
milliseconds per frame, and OpenCV's detector also returns their exact
corners, which are used to draw them on the dashboard. The dictionary used,
4×4 with 50 markers, has large cells that survive blur, and 50 signs are more
than a home needs. OpenCV's ArUco module is already installed as part of the
face-recognition stack, so this adds no dependency.

Range estimate: the Pi Camera Module 2 sees 62.2° horizontally. At 640 pixels
wide, a marker printed 14 cm across is about 74 ÷ d pixels wide at d metres.
How small a marker OpenCV can still decode depends strongly on sharpness.
Perfectly sharp synthetic markers decode even at about 14 pixels. With
realistic blur (a marker downscaled with smoothing, or with blur and noise
added), decoding became unreliable below about 30 pixels. A 14 cm sign
therefore reads to about 2 to 2.5 m under realistic conditions. This is a
desk estimate from synthetic images; the real limit with the Pi camera must be
measured (see the acceptance checklist in `TESTING.md`). Markers smaller than
24 pixels (about 3 m) are ignored, so a sign across a large room does not
trigger.

### 6.5 Written directions instead of computed ones

Two ways to produce directions were considered:

- **Computed from a floor plan:** draw the house accurately, place every sign
  with its facing direction, and compute "turn left" from the geometry. This
  needs an accurate plan and an exact facing angle for every sign. A small
  error produces a wrong turn, and the sentences come out mechanical.
- **Written by the caregiver (chosen):** for each pair of neighbouring signs,
  the caregiver writes one sentence for someone standing in front of the
  sign, for example "The bathroom is the second door on your right." These
  sentences are robust, personal ("the blue door", "past the photo of your
  wedding"), and in the family's own words. A home with four or five signs
  needs about 6 to 10 sentences.

The sentences form a graph: signs are nodes and sentences are one-way edges.
A trip is the shortest path through the graph by number of signs
(breadth-first search). The device speaks one sentence per sign reached. If
the wearer takes a wrong turn and reads a sign that is not on the route, the
route is planned again from that sign.

### 6.6 Naming rooms as well as guiding

For a person with dementia, the confusion that matters most is often not
finding the door but forgetting what a room is for. So every sign also names
its room when it is first seen ("This is the kitchen."), optionally followed
by a caregiver note ("Your tea things are in the cupboard by the window.").
This mirrors the face feature: CogniSight names the people and the places in
the wearer's life.

### 6.7 The floor plan editor

The caregiver can draw the home: walls, doors, room names, and where each
sign is placed. The plan is not used to compute directions (see 6.5). Its
purpose is planning and explanation:

- Each placed sign draws a shaded wedge (70° wide, 2.5 m long) in front of it,
  showing where the wearer must stand for the camera to read it. This helps
  decide where to stick signs.
- The written directions are drawn as arrows between placed signs, so the plan
  doubles as a route diagram.
- During a trip, the route is highlighted, and the sign of the wearer's
  current room is marked.

### 6.8 Indoor location for the caregiver without a camera feed

Because the device knows the last sign it read, the dashboard can say "In the
kitchen since 2:14 pm" and list room changes during the day. This gives the
caregiver what the camera-feed idea was trying to provide, but without
watching the wearer.

## 7. The caregiver dashboard

- **Built once, served by the Pi.** The dashboard is a SolidJS app. The built
  files are committed to the repository, so the Pi never needs Node.js or a
  build step.
- **Phone first.** Caregivers check on someone from their phone. Under 760
  pixels wide, navigation moves to a bottom tab bar, and touch targets are at
  least 44 pixels.
- **Subtitles of what the wearer heard.** Observers (family, or examiners in a
  demonstration) cannot hear the earphones, so the live page shows the last
  spoken sentence under the camera picture.
- **Accessible type and colour.** The typeface is Atkinson Hyperlegible Next,
  designed by the Braille Institute for low-vision readers and bundled so it
  works offline. Colours have fixed meanings: moss green for recognised and
  working, marigold for unknown or approximate, and blue for rooms and routes.
- **No login.** Anyone on the same Wi-Fi network can open the dashboard. This
  keeps a demonstration simple but is not acceptable for real use; a login and
  HTTPS are listed as future work.

## 8. One program, one command

Earlier there were separate commands for watching the camera and serving the
page. CogniSight now runs as one program (`cognisight start`) with background
threads for the camera, face recognition, sign reading and speech, plus the
web server. The team is not primarily software engineers, so one command and
one log keep running and debugging simple. Each part fails on its own: if the
camera, face recognition, speech or the network is missing, the rest keeps
running and the dashboard's Device page says what is wrong.

Installation is one script (`setup.sh`). It installs system packages, creates
the Python environment, applies a numpy version constraint that Picamera2
needs on Raspberry Pi OS Bookworm, installs everything, downloads all models
so the device can run offline, and saves a test photo from the camera.

## 9. Things deliberately not built

| Idea | Why not (yet) |
|---|---|
| Streaming the camera to a cloud server for remote viewing | A new server dependency, privacy concerns, and the room tracking from signs covers the main need |
| Recognising rooms from the camera picture without signs | Needs a trained room classifier and labelled photos of each home. Signs are reliable today. |
| Continuous turn-by-turn indoor guidance | Needs positioning between signs (an IMU or beacons) |
| Walking directions outdoors | Needs a working GNSS receiver |
| Login, HTTPS, multiple caregivers | Out of scope for the demonstration; needed before real use |
