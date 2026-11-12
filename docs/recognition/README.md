# Contextual facial recognition — issue #2

This is a fresh, isolated module. It has **not been qualified on Raspberry Pi**.
Local policy tests exercise storage, matching, tracking, context, queueing and
security. They do not establish biometric accuracy, model inference performance,
headset behavior, or suitability for an individual wearer.

## Hardware and software baseline

- Raspberry Pi 5, 8 GB; suitable power supply and cooling for sustained inference.
- Camera Module 2 with a standard 15-pin to mini 22-pin CSI cable. Power off before
  connecting. Use either CAM/DISP connector. Record the sensor actually detected.
- USB headset with both microphone and playback. Pi 5 has no analogue audio jack.
  Wired earphones need a USB adapter supporting microphone input, not output only.
- Initial qualification baseline: 64-bit Raspberry Pi OS Bookworm and its system
  Python 3.11. Other OS/Python combinations need their own qualification; do not
  replace an existing OS automatically. Native camera packages must match Python.
- A monitor/browser on the Pi for caregiver setup. The wearer uses audio only.

Official references:
[Camera installation](https://www.raspberrypi.com/documentation/accessories/camera-software.html),
[Picamera2](https://github.com/raspberrypi/picamera2),
[OpenCV YuNet/SFace](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html),
[Vosk](https://alphacephei.com/vosk/install),
[Piper](https://github.com/OHF-Voice/piper1-gpl),
[PortAudio Python binding](https://python-sounddevice.readthedocs.io/en/latest/installation.html).
The local speech pipeline separation also follows the pattern documented by
[Home Assistant](https://www.home-assistant.io/voice_control/voice_remote_local_assistant/).
These references establish interfaces, not the performance of this application.

## Installation on the Pi

Run these from the checkout on the Pi, as its ordinary user:

```sh
sudo apt update
sudo apt install python3-venv python3-picamera2 libportaudio2
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install -e '.[vision,audio,dev]'
cognisight doctor
rpicam-hello --list-cameras
rpicam-still --nopreview -o /tmp/cognisight-camera-check.jpg
cognisight devices
```

Remove the temporary camera-check image after inspecting it. Setup uses the
network; installed runtime does not. Use exactly one OpenCV wheel package in the
venv; importing an older apt cv2 must not silently win. `Vision.start` rejects
incompatible OpenCV versions. Never pip-install libcamera as a replacement for
the Raspberry Pi OS camera packages.

Install models explicitly:

```sh
python scripts/fetch_models.py --destination models
cp config.example.json config.json
```

The fetcher records source revisions and SHA-256 hashes in models/manifest.json.
Set config.json's model_version to `sface:` followed by the recognizer file's
SHA-256. Select the actual unique USB input/output names reported by
`cognisight devices`; do not use `default`. Relative model paths resolve relative
to config.json. Model downloads and private state are ignored by Git.

Initial threshold/margin values are provisional for enrollment consistency.
Keep `calibrated: false` until held-out evaluation succeeds; the module refuses
named runtime announcements while uncalibrated. Do not copy the OpenCV LFW
threshold into deployment and assume it is calibrated for this camera/gallery.

```sh
cognisight password
cognisight run --config config.json
```

Visit http://127.0.0.1:8765 in a browser on the Pi and sign in. The password is
prompted interactively, never placed in a command line. State defaults to
`~/.local/share/cognisight` outside the checkout; use matching `--state-dir` for
password and run if overriding it. Password rotation requires a service restart
to invalidate old browser sessions. Bind is loopback only; no remote enrollment.

## Enrollment and wearer behavior

Start enrollment; capture ten accepted, modestly varied face views. Only one
person may be visible. The tool rejects small, blurred, dark, cropped or severely
turned faces and samples inconsistent with the first accepted identity. Review
the person's name/relationship/note, confirm identity, and save. Additional-sample
sessions add ten samples to an existing identity, up to fifty total. Recognition
announcements are suspended during enrollment; cancel discards transient samples.
An enrollment session expires after fifteen minutes.

The tool edits profiles, disables recognition, permanently deletes profiles and
associated history, and clears encounter history. It is a setup interface, not
the project's broader caregiver dashboard. All profile text is caregiver supplied.
No conversation recording, generated personal context, or raw image storage occurs.

Automatic speech gives a name and relationship after three consistent processed
observations. It has a sixty-second per-person cooldown. Unknown/ambiguous matches
are silent unless the wearer asks. Requests always require a confident target.

Say the following English phrases with the configured prefix:

- “Computer, who is this?”
- “Computer, tell me more.”
- “Computer, when did I last see them?”
- “Computer, repeat.”
- “Computer, stop.”
- “Computer, pause recognition.”
- “Computer, resume recognition.”

`computer` is the stock-model prefix because `cogni` may be absent from the Vosk
lexicon. A configured prefix must be one word; every command word is checked
against the speech model at startup. `vocabulary_missing` requires a compatible
model/prefix; it must not be ignored. This is constrained command recognition,
not a separate wake-word detector. During playback only stop is actionable.
Actual accent/noise accuracy and self-trigger rejection need headset tests.

No overlapping speech is allowed. Leaving view, disabling/editing a profile,
stop, pause, and enrollment invalidate queued identity responses. A follow-up
expires after ten seconds without confirmed observation; a new identity request
needs a currently visible face. With similarly prominent faces, face one person.

History is a previous **recorded recognition**, never proof that a conversation
or meeting occurred. Ten seconds of absence ends an encounter; history expires
after thirty days. Timestamps require a sane clock and systemd-timesyncd's
volatile synchronization marker. Without verified clock synchronization,
recognition still works but time-based history is unavailable. Times are spoken
in UTC to avoid pretending the Pi has the wearer's timezone configured.

## Testing and qualification

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
# Or after installing dev dependencies:
pytest
python scripts/qualify.py --help
python scripts/evaluate_recognition.py --help
```

Tests skip native/browser integration when required dependencies are absent;
this is a visible gap, not a pass. Run the full suite again on the Pi. Keep all
consented evaluation faces/embeddings and recordings outside the checkout in a
private directory. Never commit biometric evaluation fixtures or real profiles.

The evaluation tool consumes separate calibration/evaluation encounters and
selects a threshold/margin only on calibration. Follow its --help and the
qualification guide. It reports data-kind/participant coverage; synthetic
embeddings cannot qualify real recognition. Transfer the selected threshold and
margin into config only after evaluating the intended camera and gallery.

Save a dependency lock from the qualified Pi, not this development Mac:

```sh
python -m pip freeze > qualification-private/python-lock.txt
```

Also record apt package versions, OS image/release, camera sensor, models'
manifest, exact headset, sampling rates, power, cooling, and test conditions.
Future installs must use those exact validated dependencies and repeat checks.
The broad ranges in pyproject.toml are not a claim of a qualified environment.

## Operation and recovery

The runtime alone owns the camera. Its latest-frame mailbox drops superseded
frames; capture is 640x480/15 FPS, recognition targets 5 Hz and up to four faces.
Inference may be slower: measurement is mandatory. Models use CPU only.
Enrollment and inference are serialized. Gallery snapshots refresh after edits.

Headset routes require explicit USB names. Disconnects clear pending speech and
retry every five seconds; there is no default-speaker fallback. A changed index
requires reconnection. Missing camera/model/dependency/storage appears as degraded
health; no synthetic “live” recognition is substituted. Camera restart is bounded
and cannot create a second owner. Logs rotate at 1 MB with three backups and omit
names, context, vectors, and transcripts. Use the health page/doctor for diagnosis.

For startup on boot, adapt deploy/cognisight.service paths to your checkout,
copy it to ~/.config/systemd/user/, then use `systemctl --user daemon-reload` and
`systemctl --user enable --now cognisight`. Configure user-session audio access
and any required camera/video groups on the Pi. Test service startup without an
interactive shell. The unit limits memory to 4 GB and restarts on failure.

## Integration boundary

FramePacket carries BGR pixels, frame ID, monotonic time and optional verified UTC.
Recognition events carry schema version, event ID, track/person ID, confirmed/lost
state, optional UTC and model version. Events contain no images, vectors or profile
notes. Runtime.subscribe returns a bounded module-local queue; callers must handle
old events being dropped and unsubscribe when done. Health is available via
Runtime.status. This is not a new shared HTTP API or message broker. Agree external
interfaces with Jahnvi through #6 before cross-module integration.
