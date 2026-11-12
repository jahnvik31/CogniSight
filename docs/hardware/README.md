# Hardware setup and qualification

Start with the [simple SSH runbook](PI-RUNBOOK.md). It uses `jahnvi@cognisight.local`, preserves the existing Pi installation and gives expected results and failure actions for each step. Read [the approved scope](ISSUE-7-PLAN.md) for detailed constraints.

**Physical acceptance is pending.** These tools have been tested with synthetic inputs on the development computer, not the user's Pi. Issue #7 still needs real camera detection, a visible preview, a captured still, native model execution and observed performance. No device or OS compatibility is certified here.

| Item | Known | Still needs checking on the physical device |
|---|---|---|
| Pi | Reported Pi 5 8 GB, Raspberry Pi OS 64-bit | Exact OS release, Python, architecture, supply, cooling, disk space |
| SSH | User `jahnvi`, hostname `cognisight` | Reachability, host fingerprint and actual IP if mDNS fails |
| Camera | PCB says Camera V2.0; free ribbon end shows 22 contacts | Hidden camera-end contacts, cable fit and detected sensor; do not infer sensor from label |
| Audio | AUX headset, setup deferred | USB sound adapter with compatible output and microphone input; headset mic/plug compatibility |
| Positioning | Reported SIM A7670C MODULE WITH RS232 | Exact carrier manual, GNSS capability and data interface; keep navigation disabled until verified |
| Caregiver phone | Same Wi-Fi | Phone OS, trusted Caddy certificate, actual login/status/expiry |

## Diagnostic commands

`cognisight doctor` only checks package discoverability. `cognisight doctor --native` imports required dependencies in eight isolated subprocess probes, each with a ten-second timeout. The vision probe also requires supported OpenCV and face APIs. It acquires no camera, microphone or receiver. A successful import check does not qualify hardware. Native output is captured, and only dependency state and error class are published.

For real smoke checks, stop the runtime first. Save inventory separately before configured smoke, as shown in the runbook. `scripts/qualify.py` reports imported NumPy/OpenCV versions separately from installed distribution versions, requested capture settings, elapsed processing window, frame/face-observation counts and a sensor family only when available from the allowlisted `Model` property. It does not dump camera metadata or identifiers.

A zero-frame check fails. An empty scene can pass capture/detector smoke while `recognizer_features` and recognition acceptance stay pending. At least one accepted face observation proves SFace feature execution, not identity correctness. The requested sampling duration is not a hard timeout for native capture/inference. A native hang/crash can prevent smoke reporting and cleanup; the separately saved inventory survives.

Private JSON reports are mode 0600 and must remain outside Git (for example `qualification-private/`). No raw frames, voice, names, coordinates or camera identifiers belong in a shared report. Review every report before sharing it.

## Acceptance record

| Check | State |
|---|---|
| Isolated diagnostic and qualification policy unit tests | Implemented; development results in the contributor handoff/validation record |
| Actual boot/reboot/SSH | Pending hardware |
| Actual camera sensor/modes, still and human-visible preview | Pending hardware |
| Actual apt/venv/model imports and versions | Pending hardware |
| Actual face feature inference and accuracy/latency | Pending hardware |
| USB adapter playback and microphone | Pending adapter selection/configuration |
| GNSS fixes and phone HTTPS | Pending hardware identification/device tests |
| Combined load, offline operation, memory, two-hour soak, reconnect | Pending; see [release gates](../recognition/QUALIFICATION.md) |

Keep native package versions and model manifests from an actual passing Pi. No speculative dependency lock is provided: a Mac resolver cannot certify the Pi's apt/native ABI. Indoor issue #5 remains deferred.

The runbook follows the [official camera instructions](https://www.raspberrypi.com/documentation/accessories/camera-software.html) and [Picamera2 installation guidance](https://github.com/raspberrypi/picamera2). These describe supported setup practices; they do not establish this particular camera cable, OS environment or headset as tested.
