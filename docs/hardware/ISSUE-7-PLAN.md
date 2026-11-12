# Raspberry Pi 5 and camera qualification implementation plan

> **For agentic workers:** After user approval, use `superpowers:executing-plans` or the user's chosen execution method task by task. The user approved this software implementation and pushing the release to main on 12 November 2026. Physical-device actions remain subject to actual access and the checkpoints below; no OS replacement is planned.

**Goal:** Make the actual Pi 5 development setup reproducible, diagnose native dependency failures honestly, and collect real camera/recognition evidence for [issue #7](https://github.com/jahnvik31/CogniSight/issues/7).

**Architecture:** Keep the existing Picamera2/OpenCV recognition runtime and its sole camera ownership. Add explicit, bounded diagnostic probes and extend the existing qualification tool; document a staged SSH workflow that preserves an already configured Pi. No replacement recognition module, cloud inference, or new service framework.

**Tech stack:** Raspberry Pi 5 8 GB, Camera Module 2, Raspberry Pi OS camera packages, system Python plus a virtual environment, NumPy/OpenCV YuNet/SFace, Vosk/Piper/sounddevice, existing Waitress/Caddy deployment.

**Spec:** Live issue #7, repository `AGENTS.md`, `README.md`, `docs/recognition/README.md`, `docs/recognition/QUALIFICATION.md`, and the approved session scope. `PI-RUNBOOK-DRAFT.md` is the proposed user-facing procedure, not evidence that its commands have run on hardware.

## Approval and facts still needed

Status: **Implementation approved by the user. Software tools and the final runbook are implemented; target-hardware acceptance remains pending. No target hardware accessed.**

Implementation: opt-in native diagnostics, measured smoke metadata and separate recognizer-feature evidence are present. Use [PI-RUNBOOK.md](PI-RUNBOOK.md) and [the hardware status](README.md). The checklist below records the original approved scope, not proof of physical execution.

1. User confirms the Pi is already set up with Raspberry Pi OS **64-bit**. Preserve this installation. First authorized SSH session must identify exact release/image and Python version before any installation; Bookworm versus Trixie remains unknown. No reflash is planned.
2. User confirms SSH username **`jahnvi`**, hostname **`cognisight`**; use `ssh jahnvi@cognisight.local` when mDNS works, otherwise the user's approved `REPLACE_PI_IP` placeholder. Record laptop OS and actual IP when available. No password, private key, Wi-Fi password or authentication secret should be sent in chat or written into instructions.
3. User has an **AUX headset**, not a USB headset; audio setup is deferred. Pi 5 has no analogue headset jack. The current implementation needs a verified USB sound adapter with playback and, if the headset has a microphone, compatible microphone input/plug wiring. Audio acceptance stays pending until that adapter and microphone path are selected and tested. The board is described as **“SIM A7670C MODULE WITH RS232”**; exact carrier/vendor/manual, GNSS capability and interface levels still need verification. Do not connect RS232 directly to GPIO or assume TTL-level UART. Photos show a camera PCB marked **Camera V2.0** and a cable marked **HBV-Raspberry15DFPC**. Root and independent photo review count **22 exposed contacts at the free end** with high confidence; the inserted camera-end contacts are hidden. This is consistent with a Pi 5 cable candidate, but pitch/pinout/fit are not certified from photos. The PCB label does not prove an official Camera Module 2 or a particular sensor; identify the actual sensor with `rpicam` later. The 19:54:15 image is an Imager settings screenshot, not a board photo or proof of the installed OS. Confirm the required mini-22-pin to standard-15-pin cable, power and cooling before connection.

If answers are unavailable, finish software/doc deliverables after approval and mark physical acceptance **pending**, rather than manufacture a successful report. No remote device action is implied merely by hardware ownership.

## Global constraints

- Fresh modules only; do not copy reverted history or replace functioning implementations.
- Indoor issue #5 is skipped entirely; no indoor implementation or marker work.
- Preserve the approved Monday-inspired caregiver UI and existing recognition/navigation behavior.
- Runtime owns the camera; diagnostic capture and qualification run only after stopping it. GPSD alone owns the GNSS receiver. No competing camera/GNSS processes.
- #6 owns shared contracts, lifecycle semantics and cross-module permissions policy. #7 verifies device access for the chosen actual service account and documents it. #8 owns complete end-to-end acceptance; #7 may provide hardware evidence without claiming #8 complete.
- GNSS positioning is local verified GPSD status/location only, with no routes. No guessed UART pins, voltage, baud rates or modem AT commands.
- User's AUX headset is not directly supported by Pi 5/current USB-only adapter validation. Defer audio configuration until a suitable USB sound adapter (including microphone input when needed) is identified. USB input/output then require explicit unique device names. Never fall back to HDMI/default/loudspeaker playback.
- Enrollment remains `127.0.0.1:8765`; caregiver backend remains `127.0.0.1:8766` behind same-Pi HTTPS. Never proxy enrollment or open GPSD to the LAN.
- Initial qualification candidate is 64-bit Bookworm/system Python 3.11. Current Raspberry Pi OS downloads use Trixie, so do not equate latest OS with this project's validated baseline. Existing Trixie/Python 3.13 needs a separate compatibility assessment, particularly `numpy<2`, OpenCV wheel availability and apt-camera ABI compatibility.
- Install Picamera2/libcamera with matching OS packages, use `venv --system-site-packages`, never `pip install libcamera`, never `sudo pip`, and never bypass externally-managed Python protections.
- Exact apt/Python/model versions are captured on the actual passing Pi. Broad dependency ranges or a lock generated on the Mac do not establish compatibility.
- Real images, voices, names, locations, private keys, configuration, account identifiers, serial numbers and patient records never enter Git. Reports contain only non-identifying evidence; private snapshots remain outside tracked files.
- After approval, local commits use `jahnvik31 <jahnvikotangale@gmail.com>`. No push, merge, issue closure or remote publication until the user authorizes the relevant later stage.

## Review focus

1. A package is discoverable but fails to import due to native/NumPy ABI: native check must fail explicitly without crashing the doctor parent (Task 1).
2. A probe hangs or native library exits abnormally: bounded subprocess timeout/failure must preserve a diagnostic report (Task 1).
3. Camera busy, absent or not producing a frame through a normal Python error: qualification records failure, attempts resource cleanup, and never silently passes a zero-frame smoke test; native hangs/crashes are a separate explicit limitation (Task 2).
4. AUX headset without a verified USB audio adapter, or wrong/missing USB input/output: audio stays pending or fails explicitly and cannot pass from inferred default playback; human confirmation and actual command receipt remain required (Task 2).
5. A report destination aliases config/trials or contains private data: preserve protected files, atomic mode-0600 publication and redaction; tests cover the new fields without adding recordings (Task 2).

## File map

| File | Planned responsibility |
|---|---|
| `src/cognisight/recognition/diagnostics.py` (new) | Isolated native import probes and non-identifying import results; no hardware acquisition or installation |
| `src/cognisight/recognition/cli.py` | Preserve cheap `doctor`; expose explicit `doctor --native` option |
| `tests/test_diagnostics.py` (new), `tests/test_cli.py` | Native failure/timeout/redaction and backwards-compatible CLI checks |
| `scripts/qualify.py`, `tests/test_tooling.py` | Honest camera smoke result, environment/version evidence and protected output behavior |
| `docs/hardware/README.md` (new after approval) | Hardware inventory/checkpoints, final qualification state and report links |
| `docs/hardware/PI-RUNBOOK-DRAFT.md` | Reviewed draft; promote content to `PI-RUNBOOK.md` only after approved implementation/command verification |
| `docs/recognition/README.md`, `docs/VALIDATION.md`, root `README.md` | Link the final runbook and distinguish software verification from physical acceptance |
| `pyproject.toml` or `deploy/constraints-pi-bookworm.txt` | Change only if an actual resolved/native-tested baseline requires narrower package versions; no speculative pins |

No production file changes occur in this planning stage. Coordinate CLI-file edits with #6 before execution.

## Task 1: Diagnose real native imports without acquiring devices

**Interfaces:** Preserve `doctor() -> dict` and `cognisight doctor` behavior. Add `native_report(timeout_seconds: float = 10.0) -> dict` in `diagnostics.py`; it returns `schema_version: 1`, `release_qualified: false`, and a dependency map. Each entry has `state` (`passed`, `missing`, `failed`, `timeout`) and `error_type` (exception class or null). No raw exception text, stderr, traceback, absolute path or environment dump. `doctor --native` returns 0 only when every required probe passes, 1 on missing/failed/timed-out dependency, 2 on invocation/reporting error. It never starts camera/audio/GPSD, installs packages, downloads models or changes config.

- [ ] Add tests asserting plain doctor does not import hardware, native success does not certify hardware, and native failure is different from `find_spec` success.
- [ ] Add deterministic child-process stubs for missing package, ordinary exception, abnormal exit and timeout; assert no raw private sentinel in JSON/stdout/stderr and parent survives. Test required dependencies: picamera2/libcamera, cv2/numpy, vosk, piper, sounddevice, Flask/Flask-WTF/Waitress.
- [ ] Run `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_diagnostics.py' -v`; confirm new tests fail before implementation.
- [ ] Implement probes with `sys.executable` and argument arrays, fixed allowlisted import names, bounded timeout, captured child output, and no shell invocation. Probe cv2/NumPy together and check existing `Vision.supported_opencv` policy; a successful module import alone is not a camera smoke check. Parent emits only sanitized JSON.
- [ ] Wire the opt-in CLI option without changing cheap doctor output/exit behavior. Run diagnostics and CLI tests, then review non-Pi behavior: plain doctor remains usable; missing camera libraries make native check fail rather than silently skip.
- [ ] Commit locally: `feat(hardware): add isolated native dependency diagnostics`.

## Task 2: Extend measured qualification evidence

**Interfaces:** Retain existing `scripts/qualify.py --output PATH [--config PATH --seconds N --interactive] [--trials PATH]`, existing `hardware_report()`, `smoke(...)` and report consumers. Additive environment fields only: native imported versions (distinct from distribution metadata), capture configuration, frame count/duration, and camera sensor/model only when read from an allowlisted camera property. Never dump camera identifiers or full metadata. Keep `release_qualified: false`. Existing exit convention stays 0 for successfully performed requested checks, 1 for failed requested check/invalid trials, 2 for CLI/output failure; inventory-only 0 proves report creation only.

**Boundedness limit:** Only Task 1's import probes run in timeout-controlled child processes. Camera/inference/audio smoke remains in-process: `--seconds` is the sampling window, not a deadline for native code. A native hang or crash can prevent its smoke report and cleanup. Run the inventory command first in a separate invocation/file, then run smoke; earlier inventory survives even if smoke cannot finish. No interactive child-process supervisor or native-hang recovery is added in this scope.

- [ ] Add tests: zero captured frames is failure; ordinary Python camera exception attempts camera cleanup; busy/missing camera reported through a Python exception gives failure and writes sanitized report. Verify a separately written inventory file is untouched by a later ordinary smoke failure; do not claim native-hang/crash containment for smoke. A valid empty-scene detector run may pass capture/detector smoke but leaves SFace feature inference unmeasured and `recognition_inference` pending. Reuse current tests for human audio confirmation, reports, trial validation and input alias protection.
- [ ] Run relevant tooling tests and confirm failing new assertions.
- [ ] Implement truthful measured smoke results. Include elapsed capture duration and requested 640x480/15 FPS capture, while keeping inference timings distinct from appearance-to-audible latency. Count actual accepted face observations returned by `Vision.detect` (which executes SFace features); only mark recognizer feature smoke measured when at least one succeeds. A positive face count proves execution, never identity correctness. Do not infer sensor name from product name or declare physical camera capture from import success.
- [ ] Preserve `pending` for accuracy, voice accuracy, stop latency, 100-profile gallery, two-hour soak, combined memory and reconnect until separately measured. Never promote `smoke_passed` to full acceptance. Record audio unavailable/failed distinctly from a deferred interactive check.
- [ ] Preserve private report handling and no sensitive native stderr. Extend unit tests using fabricated metadata, not private fixtures. Run CLI/tooling/vision/audio suites.
- [ ] Commit locally: `fix(hardware): preserve honest measured qualification evidence`.

## Task 3: Prepare and exercise the actual Pi environment

**Files:** Hardware README and runbook; dependency constraints only on demonstrated need.

**Consumes:** User-provided non-secret inventory, approved #6 contracts, Task 1/2 tools. **Produces:** A reproducible candidate install with measured limitations, or an explicit blocked/pending checkpoint. No claim of qualified environment before native tests.

- [ ] Assess existing OS, architecture, Python, package sources and spare disk space over the user's authorized SSH session. Preserve data and media. If no bootable setup exists, use Raspberry Pi Imager with a separately chosen card and chosen account/Wi-Fi/SSH settings; verify SSH host fingerprint through a trusted local channel. Never default to username `pi` or password `raspberry`.
- [ ] Record power supply (Pi 5 recommended official 27W or verified equivalent), cooling/case and cable. Shut down and remove power before installing/reseating CSI camera. Use mini-22-pin to standard-15-pin cable on either CAM/DISP connector; follow board markings/vendor instructions for contact orientation.
- [ ] List installed/available apt versions before package changes. Install only missing OS-matched prerequisites after the candidate OS is selected. Build venv using system Python and `--system-site-packages`; resolve vision/audio packages before installing. Do not assume Trixie's native camera binaries work with pip NumPy 1.x. Never change the NumPy cap blindly to make the resolver green.
- [ ] Check actual imported NumPy/cv2/Picamera2/libcamera paths privately, `pip check`, YuNet/SFace APIs and `doctor --native`; ensure exactly one intended pip OpenCV wheel wins. If installation/imports fail, stop that branch, record versions/error classes, and choose a separately approved compatible baseline or dependency adjustment. No unplanned downgrade/reflash.
- [ ] Run ordinary-user camera detection, headless capture and actual on-Pi monitor preview. Capture a non-personal scene to a private temporary directory; inspect and delete the image. SSH/no-preview capture cannot satisfy the issue's visible preview criterion. If no monitor is available, mark preview pending explicitly.
- [ ] Download models using the existing explicit fetcher, inspect manifest and set exact SFace hash. Configure audio later: after a suitable adapter is identified, enumerate USB input/output and enter their exact unique names. AUX output alone does not establish microphone capture. Retain fetcher's Vosk first-TLS-download trust limitation; repeat hash checks do not establish independent provenance.
- [ ] Run full Python tests with installed native/web dependencies, plus Node dashboard checks where Node is available. Capture actual skips/failures. Save inventory in a separate invocation before staged camera/model/audio smoke with runtime stopped. Defer configured smoke/runtime until required audio config is valid; camera command-line checks can proceed independently. With the adapter ready, start one runtime and verify clean Ctrl-C/restart. Do not force `calibrated: true` to obtain recognition announcements.
- [ ] If recognition evaluation is undertaken, use consented separate calibration/held-out sessions per the existing guide, anonymous trials and actual latency records. If not undertaken, record untested. Never use detector frame rate as recognition accuracy.
- [ ] Save private Python lock, apt package versions, OS/image/kernel/Python, sensor, headset/rates, power/cooling and model manifest. Review before any sanitized report is committed. Run a reinstall check on spare media/environment before describing a constraints file as reproducible.
- [ ] Commit verified software/docs locally: `docs(hardware): document measured Pi setup and qualification limits`. If hardware access is absent, commit only reviewed tooling/runbook with **physical acceptance pending**.

## Task 4: Finish the plain-English SSH runbook and acceptance record

- [ ] Validate every repository command and path after approved implementation. Clearly separate **On your laptop**, **On your Pi**, and **In your phone browser**. Explain every `REPLACE_...`, expected result and failure action. Never embed authentication secrets in URLs/shell commands.
- [ ] Document existing-Pi and new-media paths separately, connection diagnosis, secure local enrollment via SSH forwarding, USB-only voice, local GPSD identification gate, Caddy certificate trust, service startup/logout/reboot and recovery. Use actual account/path; do not blindly copy `%h/CogniSight` paths into an unmatched installation.
- [ ] Keep hardware capture checks separate from normal runtime. Service operation uses ordinary user permissions; inspect actual device nodes/groups/session access, grant only needed access, reconnect/relogin, retest after reboot. Never recommend root runtime or `chmod 777`. Headless user-unit startup must verify audio session and chosen lingering policy on this Pi.
- [ ] Check boot, camera, native imports, runtime startup/shutdown and phone TLS evidence against the table below. Add actual date/commit/platform conditions. Unmeasured values stay pending.
- [ ] Commit locally: `docs(hardware): finalize beginner SSH runbook and acceptance record`.

## Acceptance checkpoints

| Checkpoint | Evidence required | Current state |
|---|---|---|
| Software/tooling | New diagnostics/tooling tests plus full existing tests; report any skips; no private output | Implemented; see tests and development verification |
| Boot/network | Actual Pi identity/OS, successful normal reboot and repeat SSH connection | Pending hardware |
| Camera detection | Actual detected sensor and mode list, no competing owner | Pending hardware |
| Preview | Human sees live preview on actual Pi display | Pending hardware |
| Capture | Human inspects real non-personal still, image deleted | Pending hardware |
| Native dependencies | Real apt/venv imports, versions, `pip check`, model integrity | Pending hardware |
| Recognition | Measured actual smoke and, if performed, held-out results/latency with limits | Pending hardware |
| USB voice | AUX headset through verified USB adapter: actual output heard and microphone command detected | Pending adapter selection/configuration |
| GNSS and phone | Receiver-specific verified setup; trusted phone HTTPS and status; coordinate with #3/#4/#6/#8 | Pending identification/hardware |
| Release | Existing accuracy, gallery, offline, soak, memory and fault gates separately evidenced | Pending; not conferred by #7 smoke |

Issue #7 cannot be honestly closed from a Mac test pass or documentation alone. Record partial completion and remaining preview/device tests if access is unavailable.

## Sources and decisions

- [Issue #7](https://github.com/jahnvik31/CogniSight/issues/7): setup, camera detection/preview/capture, recognition testing and observed performance.
- [Raspberry Pi camera documentation](https://www.raspberrypi.com/documentation/computers/camera_software.html): current `rpicam-*` tools, wiring sequence and supported sensor discovery.
- [Official Picamera2 repository](https://github.com/raspberrypi/picamera2): apt installation keeps Picamera2/libcamera matched. Native dependencies require real import tests.
- [Pi getting started](https://www.raspberrypi.com/documentation/computers/getting-started.html) and [remote access](https://www.raspberrypi.com/documentation/computers/remote-access.html): boot media, Imager/SSH and host discovery.
- [Current OS downloads](https://www.raspberrypi.com/software/operating-systems/): Trixie is current; this plan's Bookworm candidate is a project choice, not a claim about the newest image.
- [Pi 5](https://www.raspberrypi.com/products/raspberry-pi-5/) and [Active Cooler](https://www.raspberrypi.com/products/active-cooler/): power/cooling inventory basis; actual sustained behavior remains to be measured.
- Existing `docs/navigation/README.md` and `docs/caregiver/README.md` are authoritative local procedures for unknown receiver setup and phone TLS. Keep their hardware gates rather than guessing.

Assumptions to confirm: user wants local same-Wi-Fi SSH operation, a private single-Pi installation, no OS erase, and documentation/tooling ready even if physical qualification must wait. The user approved the helper additions with #6; software is implemented, while actual device acceptance remains pending.
