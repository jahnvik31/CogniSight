# Outdoor GNSS positioning — issue #3

This fresh module supplies position readiness for outdoor navigation. It does
**not** calculate routes, load maps, provide turn-by-turn guidance, infer heading
at rest, send cellular data, or track the wearer remotely. Hardware qualification
is pending. The exact GNSS board model, transport and antenna remain unidentified.

## Selected integration

`NavigationService` connects to **local GPSD only**, initially 127.0.0.1:2947.
GPSD owns the receiver device. No GNSS UART/USB device is opened by the application,
and no guessed vendor/AT commands are sent. The module uses the standard library,
so it adds no Python package dependencies. GPSD's protocol-major 3 banner is checked
before accepting streamed reports. The vendor receiver and installed GPSD version
still need qualification. GPSD normally recommends its own bindings; this bounded
JSON client is a deliberate dependency tradeoff, covered by protocol tests.

[GPSD client guidance](https://gpsd.gitlab.io/gpsd/client-howto.html),
[JSON protocol](https://gpsd.gitlab.io/gpsd/gpsd_json.html),
[daemon options](https://gpsd.gitlab.io/gpsd/gpsd.html).

## Hardware setup gate

Before enabling navigation, record the board manufacturer/model/revision and
vendor documentation. Verify GNSS capability independently of any SIM slot,
connection interface, correct antenna, power and logic levels. Pi GPIO is 3.3 V
and not 5 V tolerant; do not attach unidentified UART hardware. Pi 5's primary
serial port may refer to its dedicated debug UART. GPIO UART overlays, baud rate,
I2C protocol, USB interface selection and antenna requirements must follow the
actual board documentation. Do not reuse Pi 3/4 wiring commands without checking.

[Pi GPIO electrical documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html),
[Pi serial/I2C configuration](https://www.raspberrypi.com/documentation/computers/configuration.html).

After identifying the receiver, install `gpsd` and `gpsd-clients` through the
Pi OS package manager, configure one receiver using its verified device path and
settings, and confirm the daemon listens on loopback only. Do not enable GPSD's
`-G` option, which exposes location to reachable hosts. Avoid a second daemon
competing with `gpsd.socket`; inspect the installed service configuration first.
A USB modem's AT-control port may differ from its GNSS output port.

Location acquisition must work in a clear-sky outdoor test. A powered board or
satellite count alone is not a position fix. Record actual acquisition time,
reported update cadence, fix mode and comparison with a known reference. Do not
substitute fabricated coordinates if acquisition fails.

## Application configuration

The parent runtime starts this service only when navigation is enabled. The
module's direct configuration is:

```json
{
  "enabled": true,
  "gpsd_host": "127.0.0.1",
  "gpsd_port": 2947,
  "fix_max_age": 10
}
```

Place that object under the application config's `navigation` key when the parent
runtime integration is installed. Defaults are loopback port 2947 and a 10-second
freshness limit; only finite positive freshness values up to 300 seconds are
accepted. `enabled` is owned by the parent, which must not construct/start the
service when it is false. These values do not configure the receiver itself.

The lifecycle is `NavigationService(config, on_update=None)`, `start()`,
`snapshot(now=None)`, and `close()`. The optional callback receives snapshots and
must be short/non-blocking; callback exceptions are isolated from GNSS reception.
The background worker has one-second socket waits and interruptible five-second
reconnects. Shutdown interrupts its active socket. Maximum GPSD line size is
10,240 bytes, including partial-line buffering. No location logs or recordings
are created, and only the latest/last-known fix stays in memory.

## Snapshot meaning

Every snapshot is schema version 1 and includes:

| Field | Meaning |
|---|---|
| `status` | `live`, `no_fix`, `disconnected`, `invalid`, or `stale` |
| `data_source` | `live` only for a current usable fix; otherwise `unavailable` |
| `source` / `data_kind` | `gpsd` / `live`; there is no runtime mock/replay mode |
| `latitude`, `longitude` | Current finite decimal degrees, null unless live |
| `observed_at` | Receiver UTC with timezone, or null if not reported/current |
| `age_seconds` | Age of last complete accepted fix using receive-monotonic time |
| `max_age_seconds` | Configured fix-expiry policy shared with dashboard consumers |
| `speed_mps` | Optional nonnegative receiver speed, null unless live |
| `reason` | Non-identifying state/recovery code |
| `last_known` | Separate historical fix with original UTC and current age, or null |
| `navigation` | Unavailable because a route provider is not configured |

A valid fix requires TPV mode 2 or 3 and a complete finite coordinate pair in
range. `(0,0)` is accepted when actually reported as a valid fix; it is never used
as a default. Missing optional UTC remains unknown. Supplied UTC must parse with
a timezone and plausible date. An invalid report or no-fix state immediately
removes current coordinates while retaining explicitly historical last-known
information. Disconnect does the same. Silence makes a fix stale at the configured
age; display the fix's original time and age, never label last-known as live.

GPSD can emit partial reports for the same epoch. Position-less reports and
repeated epochs do not refresh location age. An older reported epoch is invalid.
Different identified receivers on one connection are rejected rather than mixed;
configure GPSD to expose the intended board. Error estimates, satellite counts
and course over ground are not treated as guarantees of accuracy or heading.

## Testing and acceptance record

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_navigation*.py' -v
```

Fixtures use synthetic `(0,0)` and no personal location data. They validate state,
parsing, epoch/freshness, bounded transport and disconnect behavior only. A real
loopback TCP test is included but explicitly skips if the execution sandbox does
not permit socket binding. The socket-boundary simulation still exercises the
real adapter/parser; it is not hardware evidence.

Before issue #3 acceptance, on the actual Pi:

1. Record exact receiver/antenna/firmware, OS/GPSD versions, connection settings,
   device permissions, power and dependencies. Keep unique serial IDs private.
2. Establish a genuine outdoor fix and document actual first-fix time, interval,
   observed positional error, duration and conditions. Do not invent accuracy.
3. Cover no fix, obstructed sky, missing fields, stale stream, unplug/replug,
   GPSD restart, changing port enumeration, malformed data and clock changes.
4. Verify no current coordinates after no-fix/disconnect and after 10 seconds of
   valid-stream silence; recovery requires a newly accepted complete report.
5. Run with recognition/audio active and record combined CPU/memory/power effects.
6. Review dashboard/event consumers through #6: preserve current versus historical
   state and share audio arbitration instead of opening a second output stream.

Any private raw receiver capture belongs outside the checkout. If replay is used,
label it and never publish it as live; GPSD's
[gpsfake tool](https://gpsd.gitlab.io/gpsd/gpsfake.html) can drive external replay
tests, but it is not enabled as a production source here. No target receiver,
route-guidance, cellular-connectivity or on-Pi performance claim has been verified.
