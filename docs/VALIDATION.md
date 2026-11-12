# Software validation and physical acceptance

Updated 12 November 2026. The user authorized completing remaining nonphysical work, committing as `jahnvik31 <jahnvikotangale@gmail.com>`, and attempting this release to `main`. Check the actual push result; authorization is not evidence of publication. No issues are automatically closed.

## Implemented software

| Issue | Software delivered | Device evidence still required |
|---|---|---|
| #2 | Offline recognition/context/history, verified profiles, single-camera adapter, offline voice, local enrollment, calibration/qualification tools | Camera/model execution, headset adapter/microphone, consented calibration/accuracy and latency |
| #3 | Independent local GPSD client with validated fixes, source expiry and distinct last-known location | Exact reported board/manual and genuine compatible GNSS output; no routes in this version |
| #4 | Approved workspace-style caregiver UI, authenticated read-only same-Wi-Fi dashboard, CSRF/fixed sessions/proxy guards | Actual phone, trusted HTTPS, LAN access and accessibility/load |
| #5 | Deferred by user; unavailable/not_integrated | Do not implement indoor navigation in this release |
| #6 | Stable validated event IDs, isolated subscribers, capture-age freshness, cached HTTP projection, cleanup propagation, contracts and rendered editable diagram | Device shutdown/load evidence; no invented module-owner sign-off |
| #7 | Isolated native diagnostics, truthful camera/SFace smoke reporting, hardware checklist and complete SSH runbook | Actual Pi OS/native ABI, camera preview/still, sound adapter and package/model evidence |
| #8 | Eight real-component integration checks from SQLite/gallery/tracker and GPSD parsing through the authenticated Flask consumer | Real hardware/phone/TLS/combined-load acceptance |

## Latest local software results

**191 Python checks: 190 passed, one skipped. Four JavaScript checks passed.** The sole skipped check is `test_actual_loopback_stream_handshake_split_lines_and_shutdown`: this sandbox denies binding a TCP loopback listener. The parser/worker/socket-boundary tests using controlled synthetic responses pass; real listener transport still must execute in unrestricted CI/on the Pi. A skip is not a pass.

The final full run uses an isolated temporary environment on macOS arm64 with bundled **Python 3.12**, NumPy **1.26.4**, OpenCV headless **4.10.0.84**, Flask **3.1.3**, Flask-WTF **1.3.0**, Waitress **3.0.2**, Werkzeug **3.1.9**, WTForms **3.3.2**, MarkupSafe **3.0.4**, Jinja2 **3.1.6**, itsdangerous **2.2.0**, blinker **1.9.0**, and click **8.5.1**. Wheels were obtained from PyPI using the browser's network access, verified against PyPI SHA-256 metadata, and installed into the temporary environment. No global packages or Pi dependencies were changed. This is software-test evidence, not a Pi lock or native-device qualification.

Previously skipped Flask login/CSRF/session/enrollment tests, actual Waitress proxy/options parsing, and actual NumPy/OpenCV image-quality tests now run successfully. `pip check` reports no broken requirements. Source/scripts/tests compile successfully. Earlier 173-test/17-skip figures describe the previous limited host run, not the latest evidence.

From the repository root after installing the project software-test dependencies:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --test tests/dashboard.test.cjs
python3 -m compileall -q src scripts tests
```

The completion environment lives at `/private/tmp/cognisight-completion-venv` on this development machine only; the Pi runbook creates its own environment. Do not copy this Mac environment onto the Pi.

## Integration and browser evidence

`tests/test_integration.py` runs actual temporary SQLite Store, gallery matching, tracker, event subscriptions, NavigationService VERSION/TPV parsing, Runtime snapshot and caregiver Flask routes together. It verifies authenticated verified context/location, unknown/stale/invalid/unavailable behavior, independent producer failures, profile changes, lock contention, logout and fixed session expiry. Inputs are synthetic and contain no real patient/device data. The Flask client models HTTPS after proxy termination; it does not negotiate TLS.

The four Node checks execute the shipped dashboard JavaScript against a DOM boundary: source-age expiry without new polls, authentication expiry clearing, network-failure clearing/retry, and polling before recognition expiry. Actual Jinja/CSS/JavaScript were also visually rendered at 320, 390 and 1440 pixels using labelled simulated responses without observed horizontal overflow. This does not prove real phone TLS or accessibility acceptance. Active polling is 500 ms and failure retry is five seconds; actual combined Pi load still needs measurement.

See [issue #8 scope](system/ISSUE-8-PLAN.md) and [contracts](system/CONTRACTS.md).

## Package and proxy checks

A local **cognisight-0.1.0-py3-none-any.whl** builds with Python 3.12/setuptools **84.2.1**. Package checks verify required templates/styles/scripts, diagnostics/runtime modules, project metadata and CLI entry point. A temporary installed-wheel check runs the shipped CLI outside the source checkout. This supersedes the earlier unsuccessful build with the host's old setuptools 58.0.4; do not use the earlier empty UNKNOWN-wheel experiment.

The official **Caddy 2.11.9 mac arm64** archive was checked against its published release checksum. `caddy validate` successfully accepts `deploy/Caddyfile.example` with a synthetic hostname/private-network binding configuration. `caddy fmt` normalizes the file. Its redundant explicit forwarding-header warning is nonblocking; upstream host/IP trust remains restricted by Waitress. No server listener, phone certificate installation or physical Pi Caddy service is claimed. Actual device/phone deployment remains pending.

`.github/workflows/software-checks.yml` uses Python 3.11/Node 24, installs web/vision test dependencies, rejects any skipped software tests, runs the Node checks, builds a wheel and checks shipped assets. It has read-only repository permissions. **GitHub Actions software checks passed for commit `2341b42`** on the release branch: [successful run](https://github.com/jahnvik31/CogniSight/actions/runs/43267509618). That job rejects skips, so its Linux transport check and package gate ran successfully. The latest PR-head checks must also pass before merging. Local package success and remote CI are separate evidence.

## Defects reproduced and fixed

- Both Flask apps passed a timedelta as the CSRF time limit, causing valid form submission to raise TypeError. They now pass 900 seconds as required by [Flask-WTF configuration](https://flask-wtf.readthedocs.io/en/1.2.x/config/); login and explicit fifteen-minute CSRF expiry tests pass.
- Native diagnostic bytes could break decoding, and native output was retained unnecessarily. Child Python/native logs now go to the null device; only a small validated binary JSON envelope is returned, under per-probe timeout control.
- A dead capture thread could leave a retained camera owner and permit a second `start()`. Restart now requires explicit owner cleanup even after the reader exits.
- Failed measured trial gates and empty requested trial CSVs previously returned success. Qualification now returns exit 1 while preserving the private report; missing unrequested categories stay pending.
- Password setup previously accepted values longer than the login forms permit. It now enforces 12-256 characters before writing state.
- Earlier regressions fixed mutable/shared event records, stale frame completion timestamps, HTTP SQLite reads, source/session renewal, stale speech, keepalive/request-worker cleanup and failed-owner shutdown propagation. Failed cleanup prevents closing SQLite beneath a remaining owner. Actual native hangs remain a supervisor/process boundary.

## Only device and external-environment gates remain

1. Actual Pi release/Python/architecture, OS-matched Picamera2/libcamera and NumPy/OpenCV compatibility, permissions, power/cooling, reboot and package/model version evidence.
2. Real camera cable/sensor, human-visible preview, private still, native models, headset through a verified USB sound adapter, microphone and interruption latency.
3. Exact SIMA7670C/RS232 carrier/manual, genuine GNSS capability/interface and actual valid local GPSD fixes. Leave navigation disabled until verified; no guessed wiring/AT commands.
4. Same-Wi-Fi phone with trusted Caddy public root, actual HTTPS login/logout/expiry/source loss/recovery and LAN reachability.
5. Held-out recognition accuracy/calibration, genuine position/voice latency, accessibility, offline operation, reconnect and two-hour combined thermal/memory/load measurements.
6. The Mac sandbox still skips its local loopback listener check, but the skip-rejecting Linux CI job passed. The release branch was pushed and [PR #13](https://github.com/jahnvik31/CogniSight/pull/13) opened because repository rules require a PR into main. Check the latest PR/merge status; shell DNS restrictions are not an authentication failure.

## Contributor deliverables

Read [the simple SSH runbook](hardware/PI-RUNBOOK.md), [hardware checklist](hardware/README.md), [architecture](architecture.md) and [contracts](system/CONTRACTS.md). A printable [next-steps PDF](../output/pdf/CogniSight-next-steps.pdf) reproduces the maintained runbook with a short opening checklist. Its pages were rendered and visually inspected. Regenerate it after changing the runbook using `scripts/build_next_steps_pdf.py` (ReportLab is a documentation dependency only).

The architecture PNG was rendered with the official diagrams.net viewer and inspected. Daggers identify unverified hardware paths. Camera/audio smoke remains in-process; its sampling duration is not a native-hang deadline. Save inventory separately first. No raw images, voices, identities, locations or private keys are part of the shared handoff.
