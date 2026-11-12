# Available-module integration - issue #8

**Status: software integration coverage implemented; execution evidence must be recorded in [validation](../VALIDATION.md). Physical acceptance remains pending.** The user authorized finishing remaining nonphysical work on 12 November 2026. This document records that scope and the resulting test coverage; it does not introduce an additional approval gate.

Source: [issue #8](https://github.com/jahnvik31/CogniSight/issues/8), the implemented [module contracts](CONTRACTS.md), and the current runtime/navigation/caregiver source. The entire indoor module (#5) remains deferred. The user approved verified location/status first and a read-only caregiver phone on the same Wi-Fi; walking directions, cellular tracking and new indoor behavior are outside scope.

## Goal

Validate the available recognition/context and outdoor positioning flows through the actual software consumers. Leave only physical device, native model, microphone/playback, LAN certificate trust, real recognition accuracy and combined-load measurements for the contributor with hardware. Do not add another coordinator, event broker, camera owner, speech queue or public API version.

## Existing integration to preserve

The runtime already connects the recognition store/gallery/tracker and optional independent GPSD service. Recognition transitions reach bounded local subscriber queues. Current verified recognition and outdoor status enter a snapshot consumed by the authenticated caregiver application and its allowlist. The dashboard uses snapshots for current monitoring rather than replaying lossy historical events. Indoor stays explicitly unavailable / not_integrated.

The #6 fixes supply stable event identity, subscriber isolation, original capture age, bounded HTTP reads and cleanup failure handling. #7 supplies native import diagnostics and honest measured smoke reports. #8 software testing exercises those actual components together; it does not recreate them with canned dashboard dictionaries.

## Software integration checks

`tests/test_integration.py` uses a temporary real SQLite Store, real enrolled synthetic profile, real gallery matching and tracker, real Runtime snapshot, real NavigationService VERSION/TPV parsing, and the actual Flask caregiver application. The Flask client models HTTPS after local proxy termination; no actual TLS negotiation, browser, camera or receiver is claimed.

| Scenario | Verified boundary |
| --- | --- |
| Recognition confirmation and current location | A confirmed transition reaches a subscriber; verified profile/context and a valid zero-coordinate synthetic fix reach the authenticated JSON consumer |
| Unauthenticated access | Available names and coordinates remain absent from the 401 response; enrollment is not exposed by the caregiver application |
| Repeated successful polling | Recognition expires at one second and GPS at its own default ten seconds; HTTP reads do not renew either source; last-known position stays labeled historical |
| Invalid and no-fix GPS | Current coordinates clear while independently valid recognition remains available |
| Recognition component unavailable | Camera/storage health failure clears names without hiding a valid outdoor fix; readiness recovery can resume current monitoring |
| Edited profile | Store revision immediately invalidates cached names; the next distinct observation publishes the updated verified fields |
| Busy recognition producer | An inference/producer lock held by another thread cannot prevent the HTTP consumer from obtaining independent outdoor status |
| Logout and fixed session expiry | Previously available source data cannot be read through an unauthenticated/expired session |

All fixtures are explicitly synthetic. Test coordinates are the mathematical origin, not a real wearer location. Temporary profiles and credentials are test-only; no raw camera/audio/biometric fixtures are committed.

Run from the repository root after installing software-test dependencies:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -p test_integration.py -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --test tests/dashboard.test.cjs
```

The integration class requires actual Flask and Flask-WTF. Without them it reports explicit skips, never a simulated pass. CI installs those dependencies and rejects skipped software checks. Read the current [validation record](../VALIDATION.md) for the environment and latest exact counts; this plan deliberately does not duplicate a changing test total.

## Acceptance boundary

The software checks satisfy the available-component testing portion when executed successfully with real web dependencies. They establish neither physical end-to-end success nor a completed issue closure. These remain for the physical contributor:

1. Actual camera detection, visible preview, safe capture and native YuNet/SFace execution.
2. Verified USB sound adapter/microphone path for the owned AUX headset, commands, playback and stop timing.
3. Exact reported SIMA7670C/RS232 board identification, genuine GNSS support and compatible local GPSD output; keep navigation disabled until verified.
4. Trusted Caddy HTTPS on the actual phone, LAN reachability, login/logout/expiry and source loss/reconnect.
5. Held-out recognition calibration/accuracy, actual source/voice latency, offline operation, restart recovery and two-hour combined thermal/memory/load evidence.

Follow the [simple SSH runbook](../hardware/PI-RUNBOOK.md), [hardware checklist](../hardware/README.md), and [recognition qualification gates](../recognition/QUALIFICATION.md). Record actual versions and failed/pending checks. Do not close #7/#8, invent module-owner sign-off, or claim the system is qualified from software-only tests.
