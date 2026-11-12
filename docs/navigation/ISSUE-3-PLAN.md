# Issue #3 — Outdoor positioning implementation plan

**Status:** Fresh positioning implementation authorized; exact receiver and target-Pi qualification pending. The user confirmed that all modules are fresh. No reverted code is used. Owner: Sharanya; cross-module interface approval: Jahnvi through #6.

**Goal:** Obtain and validate outdoor GNSS fixes on the Pi, expose current versus last-known location honestly, and recover from receiver/daemon failures. This is the location-acquisition foundation for outdoor navigation. Route calculation, maps, turn-by-turn guidance, cellular telemetry, and emergency alerts are not implemented by this task.

## Evidence and decisions

The original [issue #3](https://github.com/jahnvik31/CogniSight/issues/3) described an audit. The user superseded that scope with a fresh implementation. Hardware inventory, location testing, input/output documentation and explicit blockers remain required.

GPSD provides a device-independent positioning service and can handle multiple serial receiver protocols. Receivers report asynchronously and do not always have a fix. This application consumes its local stream and does not assume a constant receiver output rate. [GPSD client guide](https://gpsd.gitlab.io/gpsd/client-howto.html)

Selected implementation: Python standard-library TCP client to a local GPSD daemon, protocol-major validation and bounded newline-delimited JSON. GPSD recommends its client bindings; the direct client is an explicit minimal-dependency tradeoff requiring protocol regression tests and a qualified daemon version. TPV fields are optional, multiple reports may arrive per epoch, time may be unreliable before lock, and reported error estimates have receiver-dependent meaning. Missing position fields must not refresh location age. [GPSD JSON protocol](https://gpsd.gitlab.io/gpsd/gpsd_json.html)

## Hardware facts to obtain before wiring or qualification

- Exact manufacturer/model/revision, vendor datasheet, firmware and transport: USB, UART, I2C or modem-specific interface.
- Whether this exact board has GNSS, cellular connectivity, or both; antenna connector, correct antenna, active/passive requirements and power. A SIM slot is not proof of positioning support.
- Power/current and logic voltage, UART baud/framing or USB interface roles, Pi OS release, device permissions and competing services. Never send guessed AT commands.

The Pi GPIO uses 3.3 V logic and is not 5 V tolerant. Do not attach an unidentified receiver's UART pins. [Pi hardware documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html)

Pi 5 serial naming differs from earlier boards: `/dev/serial0` may identify its dedicated debug UART, not the GPIO pins expected by an older tutorial. For a GPIO receiver, verify the selected Pi 5 UART overlay and disable the console on that receiver port without disabling needed hardware. For I2C, verify the vendor protocol and bus; avoid altering camera-related buses. USB selection must use the actual GNSS interface, not whichever `/dev/ttyUSB*` appears first. [Pi configuration documentation](https://www.raspberrypi.com/documentation/computers/configuration.html)

These choices remain blocked until the board is identified. Software implementation can proceed against synthetic GPSD fixtures without claiming the hardware works.

## Module boundaries and behavior

New code stays in `src/cognisight/navigation/`; tests are `tests/test_navigation*.py`. No changes to recognition/audio ownership or shared transport occur here.

`NavigationService(config, on_update=None)` exposes `start()`, `close()` and `snapshot(now=None)`. Config defaults: local GPSD `127.0.0.1:2947`, maximum fix age 10 seconds, socket timeout 1 second, reconnect interval 5 seconds. The freshness threshold is an engineering default, not a receiver specification.

Snapshot schema version 1 contains explicit `data_source` (`live` only for a current usable fix; otherwise `unavailable`), `status`, current `latitude`/`longitude` (nullable), `observed_at` (optional GNSS UTC), `age_seconds`, optional speed, source and reason. `last_known` is separate and retains its original fix/time/age. Public state is `live`, `no_fix`, `disconnected`, `invalid` or `stale`. Non-live current coordinates are null; historical coordinates never become live on reconnect alone. No fix, missing fields, out-of-range/nonfinite coordinates and daemon failure cannot fabricate `(0,0)` or reuse old data as current. A real `(0,0)` fix remains valid when supported by a valid report.

- Accept only TPV mode 2 or 3 with a complete finite coordinate pair in geographic range.
- Keep freshness by receive-monotonic time, independent of system/GNSS clock jumps.
- Validate UTC syntax/timezone and plausible date when supplied; missing UTC stays null, not receive time disguised as GNSS time.
- Partial TPV reports do not refresh a position; loss of fix immediately removes current coordinates.
- Never infer stationary wearer orientation from course over ground or treat HDOP as metres of accuracy.
- Use bounded reads/queues, interruptible reconnects and callback isolation. Never log raw positions, device identifiers or tracks by default.
- Keep only the latest and last-known fix in memory; no location-history database or network publication.
- Expose navigation availability as not configured until a separately approved route provider and destination workflow exist.

## Tasks and verification

1. Write state-policy tests first: valid/invalid/no-fix/partial reports; bounds including `(0,0)`; malformed timestamps; monotonic expiry; last-known retention. Implement immutable fix validation and snapshot semantics. Commit this layer independently after the full suite passes.
2. Write actual loopback TCP-server tests: VERSION/WATCH handshake, split/coalesced lines, malformed/oversized data, no-fix transition, server disconnect, reconnect and bounded shutdown. Implement the GPSD adapter without native dependencies. Commit transport independently after verification.
3. Document device inventory and exact setup commands only after receiver selection. On the Pi verify daemon/device enumeration, a clear-sky valid fix and no-fix behavior. Record actual first-fix times, update interval, fix availability and observed accuracy versus reference; do not invent guaranteed GNSS accuracy or startup deadlines.
4. Run replay and fault checks. GPSD's [gpsfake](https://gpsd.gitlab.io/gpsd/gpsfake.html) supports logfile replay for client regression tests; label all replay/synthetic output. Exercise partial/truncated lines, silence, socket failure, receiver unplug/replug, system-clock changes, multiple devices and mismatched timestamps.
5. Review the module-local snapshot contract with #6/#4 owners. Dashboard consumption must preserve live/no-fix/stale distinctions. Spoken location/navigation instructions must use the shared arbitration design, not a second independent headset owner.
6. Prepare an audit record with source inventory, verified hardware documentation, setup/dependency versions, test results, scrubbed sample state, limitations and follow-up issues. A PR references #3; no merge or issue closure without review.

## Acceptance boundaries

Dependency-free tests establish parser/state/transport behavior only. Hardware qualification requires the actual Pi 5/receiver/antenna outdoors and an installation record. The module must stop presenting live coordinates within 10 seconds of valid-stream silence, invalidate them immediately after no-fix/disconnect, recover only upon a new complete valid fix, and remain responsive during repeated failures. Test alongside recognition to measure shared CPU/memory/power effects.

Until the exact receiver is identified and tested, leave hardware acceptance criteria open. GNSS acquisition does not by itself provide routing, safe walking instructions, heading at rest, cellular communication or remote caregiver tracking. Their requirements and data providers remain separate decisions.
