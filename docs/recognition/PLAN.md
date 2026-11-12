# Approved implementation plan — issue #2

**Current status, 12 November 2026:** the software below is implemented. This
file preserves the approved design, rather than a list of unfinished coding tasks.
See [validation](../VALIDATION.md) for latest software evidence and the
[Pi runbook](../hardware/PI-RUNBOOK.md) for remaining device work. The owned AUX
headset needs a compatible USB sound adapter and a verified microphone path.

Fresh implementation; never restore reverted code. Raspberry Pi 5 8 GB,
Camera Module 2 with standard-to-mini cable, USB microphone/headset.
Offline English; 100 profiles; local browser enrollment; automatic and
prefixed voice requests. Verified profiles and 30-day encounter history.

1. Qualify hardware/dependencies: Picamera2 via apt, OpenCV 4.x YuNet
   2023mar + SFace, Vosk small English, Piper lessac medium, explicit USB
   devices. Pin artifact hashes and record installed versions on the Pi.
2. Enrollment/storage: localhost password + CSRF, 10 quality samples,
   normalized versioned embeddings, active profiles, transactional changes,
   deletion cascading to history. No persisted frames or audio.
3. Recognition: latest-frame capture 640x480/15 FPS, inference target 5 Hz,
   up to four tracks, threshold + runner-up margin, 3-frame confirmation,
   60-second announcement cooldown, 10-second absence ends encounter.
4. Audio: local command grammar, cancelable serialized speech, USB route
   validation, no fallback speaker, ignore non-stop commands while speaking.
5. Operations: supervised local service, localhost setup tool, versioned
   events and health, bounded retries/queues, private state, rotated logs.

Release gates: actual Pi offline operation; p95 recognition-to-speech <=3s;
p95 command-to-response <=2s; recognized stop-to-silence <=1s; command
accuracy >=95% (20 trials/intent/speaker); accepted correct identification
>=95%; 0 named false accepts in >=300 independent unknown encounters;
100-profile load; 2h soak; memory <4GB; no thermal throttling or queue growth.
Held-out participants/sessions and explicit accuracy coverage are required.
Synthetic embeddings establish software correctness, never biometric accuracy.

No hardware claims before measured qualification. Shared integration contracts
remain coordinated through #6. Enrollment remains loopback-only; the separate read-only caregiver dashboard is
implemented under #4. It never exposes enrollment to the phone.
