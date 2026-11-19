# CogniSight: project overview

This document describes what CogniSight is, what it does now, what was dropped
and why, and how it is built. It is written so it can be used as source
material for the project report. Statements about hardware say whether they
were tested on the Raspberry Pi or not.

## The problem

People living with dementia often fail to recognise someone they should know:
a daughter, a neighbour, a regular carer. The moment is distressing for both
people, and it repeats. The person loses confidence and independence, and
family members feel forgotten.

CogniSight is a small wearable-style device that quietly tells the wearer who
is in front of them: "This is Priya, your daughter." The aim is calm,
dignified support at that moment, not surveillance. The device helps the
moment and leaves the conversation to the people in it.

A caregiver dashboard lets family set up the people the wearer should
recognise and see what the device is doing.

## Who it is for

- **The wearer**, a person living with dementia. They hear short, gentle
  introductions in their earphones. They can say "stop" to silence it, or
  "who is this?" to hear it again.
- **The caregiver**, a family member or professional carer. They add people
  with a name, relationship, and a short note, and they check the device from
  their phone.

## Feature set (current)

1. **Contextual face recognition.** The Pi camera watches the scene. When a
   known person's face appears, the device names them with their relationship,
   for example "This is Ravi, your neighbour." Unknown faces are marked on the
   dashboard but are not announced.
2. **Spoken introductions without repetition.** A person is introduced the
   moment they are recognised, and then not again for two minutes. This
   replaces an earlier "three matches in a row" rule that felt to the wearer
   like the device was hesitating. Fewer repeated introductions is the main
   human benefit.
3. **Voice commands (optional).** "Stop" or "quiet" cuts speech off. "Who is
   this?" repeats the introduction. "Tell me more" reads the caregiver's note
   ("Visits on Sundays."). Speech recognition runs on the Pi, offline.
4. **Caregiver dashboard.** A web app served by the Pi, usable from a phone on
   the same Wi-Fi or on a monitor attached to the Pi:
   - **Live**: the camera picture with names drawn on faces, subtitles showing
     exactly what the wearer just heard, who is with them now, and a timeline
     of the day (who was seen, what was said, which commands were heard).
   - **People**: add someone by taking a photo with the device camera or
     uploading one. Edit relationship and note. Add more photos from different
     angles to make recognition steadier.
   - **Place**: an approximate location of the device (see below).
   - **Device**: camera, recognition, speech, and listening status, plus the
     address a phone can open.
5. **Approximate location.** The Pi lists nearby Wi-Fi access points and asks
   Google's Geolocation API where it is. The dashboard says honestly how the
   position was found: from Wi-Fi (typically tens of metres) or only from the
   internet connection (typically kilometres). It never presents a rough area
   as a precise position.

## What changed from the original plan, and why

The original proposal had four features: contextual face recognition, outdoor
navigation, indoor navigation, and a caregiver dashboard.

- **Outdoor GPS navigation was dropped.** The board the team had, an ADIY SIM
  A7670C, is a 4G modem, not a satellite receiver. A GNSS fix on that chip needs
  a separate antenna, and the SIM card was not bought with the module. It was
  replaced by Wi-Fi based approximate location, which needs no extra hardware.
- **Online location services were limited.** Google's Geolocation API needs a
  billing account even for the free allowance. For an Indian account, setup
  needs an identity check with PAN or Aadhaar, and a UPI prepayment does not
  complete that check. Mozilla Location Service closed to outside users in June
  2024. OpenCelliD needs cell-tower IDs the Pi cannot see, and rounds Indian
  coordinates to about 1 km. A key was eventually obtained. Google uses Wi-Fi
  only when at least two access points are visible. With fewer, it falls back
  to the internet address. In the hostel, only one access point was visible, so
  the result was the Vijayawada area, about 2.7 km wide.
- **Indoor navigation was dropped.** The earlier version let a caregiver type
  a map of rooms and preview a route. Nothing sensed where the wearer actually
  was: no beacons, no depth camera, no floor plan. For a person with dementia,
  the more relevant confusion is forgetting what a room is for, not finding a
  door. Recognising rooms with the camera ("this is the kitchen") was discussed
  as future work.
- **The face pipeline was replaced.** The first version used YuNet to find
  faces and SFace to compare them. It was never shown working on the Pi. It was
  replaced with DeepFace using the Facenet512 model, a stack a team member had
  already seen running on a Raspberry Pi 5.
- **The matching cutoff was tightened.** A reference project, VISU-X, used a
  cosine-distance cutoff of 0.70. In testing, two photos of people not in the
  gallery were wrongly named (distances 0.285 and 0.339). With a cutoff of 0.30,
  both are correctly rejected, and enrolled photos still match at distance 0.0.

## How it works

```
Pi Camera ──► camera thread ──► newest frame ──► recognition thread
                                     │                 │
                                     ▼                 ▼
                          dashboard live stream   DeepFace Facenet512
                                                       │
                                                       ▼
                                   known person? ──► announcer ──► speech in earphones
                                                       │
                                                       ▼
                                               timeline of events
Microphone ──► Moonshine speech-to-text ──► "stop" / "who is this" / "tell me more"
Wi-Fi scan ──► Google Geolocation ──► approximate location on the dashboard
```

Everything runs in one Python program on the Pi (`cognisight start`). The
caregiver dashboard is a SolidJS web app. It is built ahead of time, and the
Pi serves the built files, so the Pi needs no build tools.

### Face recognition

- Each person is a folder of photos under `data/faces/<name>/`, plus an
  `about.json` holding their relationship and a note. The photos are the record.
- DeepFace finds each face with OpenCV's detector and turns it into a
  512-number "signature" with Facenet512.
- A face in the camera is compared with every photo of every person using
  cosine distance. A person's score is their best (smallest) distance over all
  their photos, so several photos from different angles help. The face is
  named only if the best score is 0.30 or less.
- Signatures for gallery photos are cached and rebuilt automatically when a
  photo changes.
- A photo with no detectable face is refused at enrolment, so the gallery
  cannot silently fill with unusable pictures.

### Speech

Speech and listening use **moonshine-voice**, one open-source (MIT) library
that runs offline on a Raspberry Pi. It provides Moonshine streaming
speech-to-text (the tiny model is about 34M parameters) and neural voices
(Kokoro and Piper) for speech. Audio goes to the Pi's default output, so
Bluetooth earphones work once they are paired. If that library cannot load,
CogniSight falls back to the `espeak-ng` voice. If no audio works, recognition
and the dashboard keep running, and the Device page says why.

### Location

The Pi lists nearby access points with `nmcli` (it does not need to connect to
them) and sends their hardware addresses and signal strengths to Google's
Geolocation API. The API key stays on the Pi and is never sent to the browser.
Results are cached for five minutes.

## Technology

| Part | Choice | Why |
|---|---|---|
| Computer | Raspberry Pi 5 (8 GB) | Enough CPU and memory to run face recognition and speech together |
| Camera | Raspberry Pi Camera Module 2 on a 22-pin cable, via Picamera2 | The official Pi camera stack. A USB webcam works as a fallback |
| Face recognition | DeepFace with Facenet512, OpenCV detector | Previously seen running on a Pi 5. A 512-number signature gives good separation |
| Speech | moonshine-voice (Moonshine STT, Kokoro/Piper TTS) | Offline, small, Pi builds available, one library for both directions |
| Server | Python, Flask | Simple, and already used by the team |
| Dashboard | SolidJS, Vite, Leaflet maps | Fast on phones. Built once and served by the Pi |
| Location | Google Geolocation API with a Wi-Fi scan | No GPS hardware available |

## Privacy and safety choices

- Recognition, speech, and listening run on the device. Face photos never
  leave the Pi.
- Only people a caregiver has added can be named. Strangers are never guessed
  at. A strict cutoff (0.30) favours saying nothing over naming the wrong
  person.
- The wearer stays in control: one word ("stop") silences the device.
- The location key is kept on the device.
- Limitation: the dashboard has no login. Anyone on the same Wi-Fi network can
  open it. This is acceptable for a demonstration, not for real use.

## Testing and status

- 34 automated tests cover matching and the 0.30 cutoff, the embedding cache,
  rejection of photos without faces, introduction wording and the two-minute
  cooldown, voice command parsing, Wi-Fi scan parsing, honest location
  labelling, and every dashboard API route. They run without a camera or GPU.
- On a Windows laptop with a USB webcam, the full program was run end to end:
  a person was enrolled from the live camera through the dashboard API and was
  then recognised in the live picture at a distance of about 0.06, with the
  introduction generated. Location returned the internet-address estimate
  (about 2.7 km).
- **Not yet tested on the Raspberry Pi:** the CSI camera under this program,
  DeepFace speed on the Pi's CPU, moonshine-voice audio over Bluetooth, and the
  Wi-Fi scan with `nmcli`. The camera itself was confirmed working on the Pi
  with a separate Picamera2 streaming script.

## Team

- Meghana: facial recognition and contextual information
- Sharanya: outdoor location
- Jahnvi: caregiver dashboard and integration
- Jahnvi and Archisha: indoor navigation (re-scoped, see above)

## Future work

- Recognise rooms with the same camera ("this is the kitchen") to replace
  indoor navigation with something that helps the wearer directly.
- Use a face detector with landmarks (YuNet or RetinaFace) for better
  alignment of tilted faces.
- Add a caregiver login and HTTPS before any real-world use.
- Stream the camera through a server, so a caregiver away from home can see it.
- Use a GNSS antenna with the A7670C module, or a dedicated GPS receiver, for
  outdoor location.
- Evaluate accuracy on a labelled set of photos of the actual family members,
  and tune the cutoff per person if needed.
