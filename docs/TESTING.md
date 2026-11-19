# Testing and verification

This document lists the evidence behind each CogniSight feature. That covers
the automated tests, the end-to-end runs, the checks of the user interface and
the installer, and, separately, what has **not** been verified yet. The last
section is an acceptance checklist for the Raspberry Pi, for the team to fill
in when the device is tested.

## 1. Automated tests

Run with:

```sh
python -m unittest discover -s tests -v
```

55 tests, all passing at the time of writing. They need only Flask, so they
run on any computer and in continuous integration (GitHub Actions runs them
on every push, then builds the dashboard). They replace the camera, face
model, speakers and Google with small stand-ins, so they test CogniSight's own
logic, not the third-party libraries. One test (marker detection) uses the
real OpenCV detector when it is installed and is skipped otherwise.

### Face gallery and matching (`tests/test_faces.py`, 11 tests)

| Test | What it proves |
|---|---|
| names cannot escape the gallery | Names such as `../Priya`, blank names, names with slashes, and names over 80 characters are refused. Photo file names cannot point outside a person's folder. |
| person round trip with relationship and note | A person's relationship and note are saved and read back |
| photo without a face is rejected and not kept | Enrolling a photo with no detectable face fails, and no file is left behind |
| best photo wins and strangers are unknown | With several photos per person, the closest photo decides. A face far from everyone is "unknown" with no distance. |
| cutoff is 0.30 | Distances of 0.106 and 0.293 match; 0.375 does not |
| empty gallery names no one | Faces are still reported (as unknown) when nobody is enrolled |
| cache survives restart and rebuilds on change | Embeddings are loaded from the cache after a restart, and a changed photo is embedded again |
| deleting removes from recognition | A deleted photo or person is no longer recognised |
| hand-copied photo folder is picked up | Photos copied into `data/faces/<name>/` by hand are used |
| small box overlapping a face is dropped, but a second person is kept | The false-detection filter removes a box overlapping a real face, but not a separate person |
| duplicate person is refused | The same name, ignoring extra spaces, cannot be added twice |

### Speech and commands (`tests/test_voice.py`, 8 tests)

| Test | What it proves |
|---|---|
| introduction wording | "This is Priya, your daughter.", "This is Priya." (no relationship), "my neighbour" becomes "your neighbour", "the family doctor" is kept |
| speaks at once, and again only after two minutes away | The first match speaks immediately. A person seen again within 120 seconds is not re-introduced; after 120 seconds out of view they are. Another person is introduced meanwhile. |
| someone who stays in view is introduced once | Ten minutes of continuous recognition produces one introduction |
| not lost while speech is still loading | A person recognised before speech is ready is introduced once it is |
| muted says nothing, and introduces after unmute | With speech off, nothing is said, and the person is introduced once speech is back on |
| audio failure is reported, not raised | A missing audio device produces an error message on the Device page, not a crash |
| commands | "stop", "be quiet", "who is this", "who's that", and "tell me more" are understood. The device's own sentence "This is Priya, your daughter." is not mistaken for a command. |
| handle who, more, and stop | "who is this" repeats the introduction, "tell me more" reads the note, and with nobody in view the answer is "I don't see anyone I know right now." |

### Signposts and guidance (`tests/test_signs.py`, 18 tests)

| Test | What it proves |
|---|---|
| marker ids are the lowest free numbers and survive restart | Signs get marker numbers 0, 1, 2…; a deleted number is reused; data persists in `signs.json` |
| names are unique and required | Two signs cannot share a name; blank names are refused |
| route follows written directions | Bedroom → Hallway → Bathroom is found; a sign with no written way out has no route |
| deleting a sign removes its directions and plan place | No dangling directions or plan positions remain |
| links reject bad input | A direction to itself, to an unknown sign, or with no text is refused |
| plan is cleaned and clamped | Sizes are limited to 50 m, coordinates are kept inside the plan, angles wrap (450° becomes 90°), and unknown signs and empty labels are dropped |
| spoken destination | "take me to the toilet please" finds Bathroom through its other name; "where's the kitchen" finds Kitchen; unknown rooms find nothing |
| the | Room names are spoken naturally: "the kitchen", "the TV room", "Priya's room", "the Study" |
| walking into a room names it once | "This is the kitchen. Tea is by the window." is said once, and again only after 2 minutes away |
| staying in a room names it once | Ten minutes in front of the same sign produces one announcement |
| rooms are not named before speech works | A sign seen while speech cannot be heard is announced later, not skipped |
| going back past a sign does not repeat it in the route | A detour and return leaves the route as Bedroom, Hallway, Bathroom |
| guided trip, one step per sign | The full trip: the first step at the bedroom, the hallway step, no immediate repeat, a repeat after 30 s of lingering, "You're at the bathroom.", arrival shown for 20 s, then cleared |
| wrong turn is rerouted | Seeing the Kitchen sign while heading to the Bathroom re-plans via the Hallway |
| no route is said plainly | "I don't know the way to the kitchen from here." |
| old sighting does not count as here | A sign seen 5 minutes ago does not count as the wearer's position |
| unknown marker is ignored | A marker with no sign does nothing |
| printed marker is read, and far ones are ignored | The real OpenCV detector reads a generated marker, and ignores one too small (too far away) to act on |

### Location (`tests/test_location.py`, 7 tests)

| Test | What it proves |
|---|---|
| parse nmcli unescapes and dedupes | The Wi-Fi scan output is parsed correctly. Each access point appears once, with its strongest signal. |
| no key is not configured | Without a key, Google is never called and the page explains how to add one |
| two access points are sent as Wi-Fi | With two or more access points, they are sent and the result is labelled Wi-Fi |
| one access point falls back to the internet address | With one access point, none are sent and the result is labelled "internet address" |
| wide answer is labelled ip even with Wi-Fi | An answer with a 2.7 km radius is never presented as a Wi-Fi fix |
| Google error is reported | Google's error message is shown to the caregiver |
| locator caches until forced | Results are reused for 5 minutes unless "Check again" is pressed |

### Dashboard API (`tests/test_server.py`, 11 tests)

These use the real web server and runtime with a stand-in for the camera. They
cover:
- adding a person by upload and by camera capture;
- refusing photos without a face, leaving no half-saved person;
- a capture with no camera, which is refused and saves nothing;
- duplicate and invalid names, and wrong file types;
- editing, adding and deleting photos and people, with path tricks refused;
- status, live and events with no camera;
- the full sign workflow: creating signs, writing directions, saving the plan, starting a trip, the room and trip state, and stopping and deleting;
- unknown API routes;
- serving the dashboard for every page address.

## 2. End-to-end runs

These ran the real program on a Windows laptop. They are not Pi results.

1. **Face recognition with a webcam.** The program found the laptop webcam,
   loaded Facenet512, and checked each frame in about 0.11 seconds on the
   laptop CPU. A person was enrolled by capturing from the live camera through
   the dashboard API. They were then recognised in the live picture at a
   cosine distance of about 0.06, the green box and name were drawn on the
   stream, and the introduction was logged. A capture with nobody in front of
   the camera was correctly refused with "No face was found".
2. **The false-detection fix.** On the live picture, the OpenCV detector drew
   an extra "Unknown" box on a pillow overlapping the real face. The overlap
   filter was added because of this.
3. **Speech.** On the laptop, the Kokoro voice loaded in 54.5 seconds the first
   time (including the download) and spoke "This is Priya, your daughter." in
   3.3 seconds from request to end of playback. The speech-to-text model was
   also downloaded and loaded.
4. **A guided trip through the real program.** A simulated camera showed the
   Hallway sign, then the Bathroom sign. The camera, sign and speech threads
   ran as in normal use. The device said "This is the hallway", then "The
   bathroom is the second door on your right" when the trip started, then
   "You're at the bathroom", and drew the sign's outline and name on the
   camera picture. This also showed that sign guidance works when face
   recognition fails to load.
5. **Printed signs decode.** The print page was rendered in a browser and
   captured as an image. OpenCV's detector read all four markers from that
   image with the right numbers (Bathroom 2, Bedroom 0, Hallway 1, Kitchen
   3), so the printed sheets match what the device looks for.
6. **Location.** With the key configured, the laptop received the
   internet-address estimate (16.49549, 80.50980, accuracy radius about 2.7 km). The map page
   showed the area circle and labelled it as approximate. A bug where the map
   stayed blank (it was measured before it was laid out) was found here and
   fixed.
7. **Phone layout.** The dashboard was rendered at 360 pixels wide. All five
   tabs, the floor-plan toolbar, the sign form, and the guide card fit without
   sideways scrolling.

## 3. Installer checks

The Pi installs Python packages for 64-bit Arm. Package resolution was checked
for that platform without a Pi:

| Raspberry Pi OS | Python | Result |
|---|---|---|
| Bookworm (numpy 1.x in the system) | 3.11 | numpy 1.26.4, TensorFlow 2.18.1, tf-keras 2.18.0, opencv-contrib-python-headless 4.11, pandas 2.3.3, deepface 0.0.105, moonshine-voice 0.1.6: all available as prebuilt Arm packages |
| Trixie | 3.13 | numpy 2.x, TensorFlow 2.21.0, tf-keras 2.21.0, opencv-contrib-python-headless 5.1, deepface 0.0.105, moonshine-voice 0.1.6: all available |

Two installer problems were found and fixed this way:
- DeepFace installs its own OpenCV package, and the project also listed
  another. Two OpenCV packages overwrite the same module, so the second was
  removed.
- On Bookworm, Picamera2 is built against the system's numpy 1.x and breaks
  if numpy 2 is installed. `setup.sh` detects this and keeps numpy below 2.

## 4. Not yet verified on the Raspberry Pi

- The Pi camera under CogniSight. The camera itself was confirmed with a
  separate Picamera2 streaming script. There is a known colour-order question
  with Picamera2's RGB888 format; `--swap-colors` exists in case faces look
  blue.
- How long face recognition takes per frame on the Pi's CPU.
- Speech speed on the Pi, and playback over Bluetooth earphones.
- Voice commands with a real microphone on the Pi.
- The Wi-Fi scan with `nmcli`, and the location accuracy in the demonstration
  room.
- The reading distance of printed signs with the Pi camera (estimated at
  about 2.5 m from desk tests).
- Running for a long time: memory use and temperature. An active cooler is
  recommended.

## 5. Raspberry Pi acceptance checklist

Fill this in on the Pi and keep it with the report.

| # | Check | How | Result |
|---|---|---|---|
| 1 | Setup completes | `./setup.sh`; note how long it took | |
| 2 | Camera photo looks right | Open `camera-check.jpg`; colours and orientation correct | |
| 3 | Dashboard opens on the Pi and on a phone | `./start.sh`; open the address shown on the Device page | |
| 4 | Live picture appears | Live page | |
| 5 | Enrol a person from the camera | People → Add a person → Take photo | |
| 6 | Person recognised; name drawn; distance | Live page; note "seconds per check" on the Device page | |
| 7 | Stranger shown as Unknown, not named | Someone not enrolled steps in | |
| 8 | Introduction heard in Bluetooth earphones | Note the delay from appearing to hearing | |
| 9 | Not repeated within 2 minutes | Stay in view | |
| 10 | "Who is this?" and "stop" work | With a USB microphone | |
| 11 | Sign read and room named | Print the Hallway sign; walk up to it; note the furthest distance it reads from | |
| 12 | Guided trip Bedroom → Hallway → Bathroom | Live → Guide them to… Bathroom | |
| 13 | Location | Place page; note Wi-Fi or internet address, and the accuracy | |
| 14 | Runs for 30 minutes | Note the temperature (`vcgencmd measure_temp`) and any errors | |
