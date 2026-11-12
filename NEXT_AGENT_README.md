# Start here: handoff for the next coding agent

**Handoff date: 12 November 2026.** Read `AGENTS.md`, this file, and the relevant issue plan before changing code. The latest user instructions take priority. The user approved #6/#7 and then requested completing all remaining nonphysical work, updating every Markdown guide, providing a PDF, and attempting this release to main on 12 November 2026. New scope still needs its own agreement.

## What the user wants next

1. **Skip indoor navigation, issue #5.** Do not add markers, indoor routing, or another camera consumer.
2. **Nonphysical software is implemented and reviewed, including #8 integration tests.** Start with actual device qualification; do not re-plan finished modules.
3. **#6/#7 software implementation is approved and present.** Do not ask for the same approval again. Physical-device checks remain pending; collect actual evidence before declaring acceptance.
4. Continue device qualification in small, tested steps using the authorized Git identity.
5. At the end, give the contributor a **simple, checked runbook**: say which commands run on the laptop and which run on the Pi, what result to expect, and what to do if a step fails.
6. The user explicitly authorized pushing this completed #6/#7 release to `main`. Check the actual push result and remote state; do not infer publication from local commits. This does not authorize unrelated future releases or force-pushes.

The contributor receiving this code has access to the physical devices. Use that access to collect evidence. Do not repeat this session's hardware assumptions as successful tests.

## Current software and issue status

| Issue | Current state | What is still missing |
|---|---|---|
| #2 — recognition/context | Fresh implementation: Picamera2, YuNet/SFace, verified profiles, encounter history, offline voice, local enrollment | Actual camera/headset execution, calibration, accuracy and performance on the Pi |
| #3 — outdoor positioning | Fresh local GPSD client; validates fixes and keeps live/last-known states separate | Confirm the actual board supports GNSS, its interface, setup and a real fix |
| #4 — caregiver interface | Read-only HTTPS dashboard; approved UI; real Flask auth/CSRF/session and Waitress tests pass | Actual Pi/phone TLS, LAN access and combined load |
| #5 — indoor | **Deferred by the user** | Keep `unavailable / not_integrated` |
| #6 — system interfaces | Software implemented: stable isolated events, capture-age freshness, cached HTTP projection, cleanup fixes, contracts and rendered editable diagram | Device shutdown/load evidence and separate team-owner review |
| #7 — Pi and camera | Software implemented: isolated native doctor, truthful measured smoke, final SSH runbook | Real Pi OS/native/camera/preview and adapter qualification |
| #8 — end-to-end integration | Eight real-component software integration checks pass through Store/Runtime/GPSD parsing/authenticated Flask consumer | Physical combined-device acceptance; no claim of actual TLS or hardware |

Everything is a fresh implementation. **Do not restore or reuse reverted code from Git history.** Earlier GitHub issue comments mention old prototypes and passing tests; those are not evidence for this checkout. Do not close issues because files exist or unit tests pass.

### Plans and guides to read

- [Issue #6 plan](docs/system/ISSUE-6-PLAN.md)
- [Issue #7 plan](docs/hardware/ISSUE-7-PLAN.md)
- [Beginner SSH runbook](docs/hardware/PI-RUNBOOK.md)
- [Printable next-steps PDF](output/pdf/CogniSight-next-steps.pdf)
- [Implemented issue #8 integration scope](docs/system/ISSUE-8-PLAN.md)
- [Architecture and editable diagram](docs/architecture.md)
- [Implemented contracts](docs/system/CONTRACTS.md)
- [Software validation and known gaps](docs/VALIDATION.md)
- [Recognition setup](docs/recognition/README.md) and [hardware acceptance gates](docs/recognition/QUALIFICATION.md)
- [GNSS setup and limitations](docs/navigation/README.md)
- [Caregiver HTTPS setup](docs/caregiver/README.md)

The final hardware runbook is the one beginner procedure. Commands were reviewed against the finished CLI, but have not been run on this Pi. The system runbook outline is only an editorial checklist. Record device results without presenting reviewed commands as tested hardware.

## Device facts: confirmed, observed, and unknown

### Pi and connection

- User reports **Raspberry Pi 5, 8 GB, Raspberry Pi OS 64-bit**.
- Pi login username: **`jahnvi`**. This is different from the GitHub username.
- Hostname: **`cognisight`**.
- Try `ssh jahnvi@cognisight.local` if the local network resolves `.local` names. The IP is unknown; use the verified address as a fallback.
- The **OS release and Python version have not been read from the Pi**. The supplied Imager screenshot shows intended settings, not proof of the installed release or successful boot.
- Preserve the installed OS, SD card and private data. Do not reflash or downgrade Python automatically.

Safe first checks, **on the Pi after an authorized connection**:

```sh
whoami
cat /etc/os-release
uname -m
python3 --version
```

Current dependency guidance starts with Bookworm/system Python 3.11. Do not assume it also works on Trixie/Python 3.13: the current NumPy `<2` constraint and OS camera packages need checking. Match installed packages before installing anything. Never `sudo pip`, pip-install libcamera, or bypass OS package protections.

### Camera and cable

- User calls it Camera Module 2. Reviewed photos show PCB text **Camera V2.0**, cable text **HBV-Raspberry-15DFPC**, and **22 visible contacts at the exposed cable end**.
- The camera-side contacts were inserted/hidden. Photos did not establish that end's count, cable pitch/pinout, exact sensor, or official-board origin.
- Standard Pi 5 CSI uses a mini 22-pin connector; standard Camera Module 2 uses 15 pins. Check the actual cable and board before connection. Read the actual detected sensor using the OS camera tools later.
- Shut down and unplug power before moving a CSI ribbon. Use current `rpicam-*` tools, not legacy `raspistill` instructions.
- Original photos were reviewed locally and are **not included in this repository**.

### Reported “GNSS” board

- User's model description: **“SIMA7670C MODULE WITH RS232.”** Manufacturer, full variant/revision, firmware and true GNSS support are still unverified.
- A similarly named [ADIY manufacturer datasheet](https://adiy.in/wp-content/uploads/2022/04/A95296_ADIY-GSM-Card-SIM7670C-4G-With-LM317_Datasheet.pdf) describes an LTE modem, RS232 and a 1.8 V UART header. This is a reference to investigate, **not confirmation that it is the user's exact board or that it provides GNSS**.
- Get clear board markings/photos and the matching vendor manual. A cellular modem, SIM slot, antenna, or cellular LBS feature is not proof of a GNSS receiver/NMEA stream.
- Do not connect RS232 directly to Pi GPIO, guess level conversion/pins, or send unverified vendor setup commands.
- Keep `navigation.enabled: false` until a suitable receiver/interface is confirmed. The software supports local GPSD; it does not configure this unidentified modem.
- User approved **location/status first**, not walking routes, turn-by-turn speech, or remote cellular tracking.

### Audio

- Latest user correction: the earphones/headset use **AUX**, not a USB headset. Audio hardware configuration is deferred.
- Pi 5 has no built-in analogue headphone jack. The existing code requires an explicitly selected USB audio input and output.
- A suitable USB sound adapter must support the needed headphone output **and microphone input**. Check whether the earphones actually have a microphone and the plug/adapter wiring match. An output-only adapter will not provide voice commands.
- Do not claim audio tested, switch to a default speaker, or remove the USB-route guard to make a test appear to pass.

### Caregiver phone

- Same Wi-Fi as the Pi; read-only monitoring, one wearer/Pi and one caregiver credential.
- Phone OS, chosen HTTPS hostname/IP, CA trust and actual browser behavior still need checking.
- Keep the approved workspace-style design. The displayed preview used **labelled simulated responses**, not the physical camera or positioning board.

## Do not break these boundaries

| Boundary | Current behavior to preserve |
|---|---|
| Camera | One owner in `recognition/vision.py`; runtime serializes enrollment/inference; no second app/camera worker |
| Face information | Caregiver-verified name/relationship/note only; no generated personal facts or conversation recording |
| Recognition | Default automatic cooldown 60 s; three consecutive observations; no named output before calibration |
| Voice | One existing AudioEngine/queue; English offline commands; stock prefix **“Computer”**; explicit requests priority 1, automatic messages 0; stop uses cancellation, not another queued message |
| Position | GPSD local only; complete finite valid fixes; no-fix/disconnected/invalid/stale never expose last-known as current |
| Dashboard | Schema 1; independent source age; currentness cannot be refreshed by HTTP polling; names/location clear on auth/network failure |
| Network | Enrollment `127.0.0.1:8765`; caregiver backend `127.0.0.1:8766`; Caddy exposes dashboard only over HTTPS 443; GPSD loopback only |
| Secrets/data | Private state outside checkout, normally `~/.local/share/cognisight`; no images, voices, embeddings, real profiles, locations, passwords, keys or tokens in Git |

The dashboard polls every 500 ms while connected and retries after 5 s on failure. Measure actual Pi load; this is not a performance guarantee. Its one-second recognition expiry and GPS configurable expiry must remain truthful.

For #6, follow the user's diagram workflow: editable draw.io file, generated from a script, source coverage checklist, XML/edge validation, rendered visual inspection, and explicit assumptions. This is a **local Pi system**; do not invent AWS services or cloud boundaries. See docs/architecture.md for the generated editable file and inspected PNG. Keep both synchronized after changes.

## Tests and the limits of the last results

The current [validation record](docs/VALIDATION.md) is authoritative:

- Python: **191 checks, 190 passed, one sandbox loopback-listener skip** in the isolated Python 3.12 environment with actual web/NumPy/OpenCV dependencies.
- JavaScript: **four passed**; Python compilation and pip dependency checks passed.
- Actual Flask auth/CSRF/enrollment/session, Waitress proxy/options and OpenCV image-quality tests now execute successfully. Eight available-module integration checks pass.
- The wheel builds with setuptools 84.2.1; shipped assets/metadata and an installed CLI are checked outside the checkout.
- Official Caddy 2.11.9 validates the example configuration locally; actual Pi/phone certificate trust and service operation remain pending.
- The next-steps PDF is generated from the runbook and visually inspected. Regenerate it after changing the guide.

The shell still cannot resolve GitHub; a failed push is not an authentication request or a successful publication. Remote CI is not claimed. The only local software skip is the sandbox denying a real TCP listener. The next contributor must rerun on the actual Pi rather than inherit Mac test results as hardware acceptance.

From the checkout:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --test tests/dashboard.test.cjs
```

The workflow in `.github/workflows/software-checks.yml` installs software-test dependencies and rejects skips. Check its actual result after a successful push. A passing CI run does not qualify hardware.

### Commands that exist now

- `cognisight doctor` — package discovery only; not proof that native packages import or devices work.
- `cognisight devices` — requires the audio dependency; lists routes.
- `cognisight password` — interactive local password setup.
- `cognisight run --config PATH` — starts configured services.
- `scripts/fetch_models.py`, `scripts/evaluate_recognition.py`, `scripts/qualify.py` — read their `--help` and existing setup docs.

`cognisight doctor --native` now runs required imports in isolated subprocesses with a ten-second timeout per group. Exit 0 means imports passed, 1 means a dependency failed/missing/timed out, and 2 means invocation/reporting error. It opens no devices and never certifies hardware.
`qualify.py --seconds` is currently a sampling window, not a hard deadline for a hung native call. The smoke report now separates capture/detector execution from accepted SFace feature execution; zero frames fail. An empty camera scene must not be described as successful SFace feature execution or identity recognition.

## Git and collaboration

- Software work was developed on **`feat/2-contextual-recognition`** and is now consolidated on local **`main`**. Identify the final release through `git log` and the actual remote state; do not treat an older UI/planning commit as the completed release.
- Start with `git status --short` and `git log -5 --oneline`. Preserve the contributor's uncommitted changes.
- Use the branch/commit the user provides after pushing. Do not assume remote main already has this work. If it has not been pushed, the runbook explains a current-tree archive/SCP transfer.
- User requested repository-local commit identity **`jahnvik31 <jahnvikotangale@gmail.com>`**. Do not use Codex as author/co-author or change global identity. Follow any explicit newer identity instruction from the user/contributor.
- Commit small, verified changes. The user authorized this release to main; do not force-push, close GitHub issues, or claim team approval automatically. Follow the usual PR workflow for later work unless the user explicitly changes it.
- Do not restore reverted prototypes or add raw device captures as tests. Use labelled synthetic fixtures and separate physical evidence.

## Before the next agent says “done”

1. Honor the completed #2/#3/#4/#6/#7/#8 software scope; keep #5 deferred. Investigate actual device failures against the current code before proposing new features.
2. Run the relevant tests and report failures/skips by their real causes.
3. Record actual device/OS/package/model versions when hardware is used.
4. Keep #5 deferred and hardware-unavailable states honest.
5. Use the supplied final runbook and PDF. Update them only where actual device evidence changes the steps; do not recreate finished documentation.
6. Keep private material out of staged files. `.gitignore` does not remove anything already tracked.
7. Report commit IDs, exact remote-push result, and pending device acceptance.
