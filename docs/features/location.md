# Approximate location

CogniSight can show a caregiver roughly where the device is on a map. The Pi
lists the Wi-Fi access points it can hear, sends them to Google's Geolocation
API, and shows the answer on the dashboard's Place page together with an
honest statement of how the position was found: from Wi-Fi (typically tens to
hundreds of metres) or only from the internet connection (typically
kilometres). The API key stays on the Pi and is never sent to the browser.

The code is in `src/cognisight/location.py`; the page is `web/src/Place.jsx`.
Tests are in `tests/test_location.py`.

> **Hardware status.** The Wi-Fi scan with `nmcli` has **not** been run on the
> Raspberry Pi. When the full program was run on a Windows development laptop,
> location returned Google's estimate from the internet address, near
> Vijayawada, with an accuracy radius of about 2.7 km (an area about 5.4 km
> across), as recorded in [PROJECT_OVERVIEW.md](../PROJECT_OVERVIEW.md).
> (`nmcli` does not exist on Windows, so the program could not send any access
> points there.)

---

## 1. Why approximate location, and not GPS

The original plan included outdoor GPS navigation. It was dropped because the
board available to the team, an ADIY SIM A7670C, is a 4G modem rather than a
satellite receiver; a satellite fix on that chip needs a separate antenna, and
the SIM card was not bought with the module. Wi-Fi-based location needs no
extra hardware: the Pi's own Wi-Fi radio can list nearby access points without
connecting to them. Other services were considered and rejected (Mozilla
Location Service closed to outside users in June 2024; OpenCelliD needs
cell-tower ids the Pi cannot see). The history is in
[PROJECT_OVERVIEW.md](../PROJECT_OVERVIEW.md).

Location is a convenience for the caregiver, not navigation. The device does
not give the wearer outdoor directions.

---

## 2. Scanning nearby Wi-Fi with `nmcli`

`scan_wifi()` runs NetworkManager's command-line tool:

```sh
nmcli -t -f BSSID,SIGNAL,CHAN dev wifi list --rescan auto
```

- `-t` asks for terse output: one access point per line, fields separated by
  colons.
- `-f BSSID,SIGNAL,CHAN` selects three fields: the access point's hardware
  (MAC) address, its signal quality as a percentage, and its channel.
- `--rescan auto` lets NetworkManager decide whether its cached scan is recent
  enough or a fresh scan is needed.
- The Pi does not need to be connected to any of these networks.

The command is given **10 seconds**. If `nmcli` is missing, fails to start, or
times out, the scan returns an empty list and no error is shown; the lookup
then proceeds with no access points (and so falls back to the internet
address, section 4).

### 2.1 Parsing the output (`parse_nmcli`)

In terse mode, the colons *inside* a BSSID are escaped as `\:` so they are not
mistaken for field separators. A typical line is:

```
AA\:BB\:CC\:DD\:EE\:01:80:6
```

The parser walks each line character by character: a backslash makes the next
character literal, and an unescaped colon ends a field. That line becomes the
fields `AA:BB:CC:DD:EE:01`, `80`, and `6`. Then:

1. The BSSID is lower-cased and must be exactly 17 characters with 5 colons;
   other lines (headers, blank lines, garbage) are skipped.
2. The signal must be a whole number; otherwise the line is skipped.
3. The channel is included if the third field is a number.

### 2.2 Converting signal quality to dBm

Google expects signal strength in dBm (decibel-milliwatts, negative numbers;
closer to zero is stronger). `nmcli` reports a quality percentage from 0 to
100. The code converts it with

```
signalStrength = round(signal / 2 − 100)
```

which maps the percentage linearly onto −100 to −50 dBm:

| `nmcli` SIGNAL | Sent to Google |
|---|---|
| 100 % | −50 dBm |
| 80 % | −60 dBm |
| 60 % | −70 dBm |
| 40 % | −80 dBm |
| 0 % | −100 dBm |

This is an approximation of the radio's actual dBm reading; it preserves the
order of strengths, which is what matters most to the location estimate.

### 2.3 De-duplication

The same BSSID can appear on more than one line. Only one entry per BSSID is
kept, the one with the **strongest** signal. In the test data, the access point
`aa:bb:cc:dd:ee:01` appears at 80 % and 60 %; the 80 % reading (−60 dBm) is
kept.

Each access point is sent in Google's format:

```json
{"macAddress": "aa:bb:cc:dd:ee:01", "signalStrength": -60, "channel": 6}
```

---

## 3. The Google Geolocation request

`lookup(key, points)` sends one HTTPS `POST` to

```
https://www.googleapis.com/geolocation/v1/geolocate?key=<GEOLOCATION_API_KEY>
```

with a JSON body:

```json
{
  "considerIp": true,
  "wifiAccessPoints": [
    {"macAddress": "aa:bb:cc:dd:ee:01", "signalStrength": -60, "channel": 6},
    {"macAddress": "aa:bb:cc:dd:ee:02", "signalStrength": -80, "channel": 149}
  ]
}
```

- **`considerIp: true`** allows Google to fall back to the location of the
  internet address the request comes from when the Wi-Fi data is not enough.
  Without it, a request with too few access points would simply fail (during
  development, a Wi-Fi-only request made where only one access point was
  visible returned HTTP 404), and the caregiver would see nothing at all.
- **`wifiAccessPoints` is included only when at least two access points were
  found.** Google's Geolocation API uses Wi-Fi for a position only when it
  receives at least two access points; a request with a single access point
  gets no Wi-Fi-based answer. Sending one would add nothing, so with zero or
  one the code sends only `considerIp`, and Google answers from the internet
  address.

The request has a **10-second** timeout, so a fresh lookup (scan plus
request) takes at most about 20 seconds. The response is read as JSON whether
the status is success or an HTTP error.

A successful answer looks like:

```json
{"location": {"lat": 16.4955, "lng": 80.5098}, "accuracy": 40.0}
```

`accuracy` is the radius, in metres, of the circle Google believes the device
is in.

---

## 4. Labelling the answer honestly: `wifi` or `ip`

The result tells the caregiver how the position was obtained, so a rough area
is never shown as a precise position. `source` is:

- **`wifi`** if at least two access points were sent **and** the reported
  accuracy is **1000 m or better** (`WIFI_ACCURACY_LIMIT = 1000.0`);
- **`ip`** otherwise.

The second condition is needed because Google can receive Wi-Fi data and still
answer from the internet address (for example, when it does not know those
access points). In that case it does not say so, but the accuracy gives it
away. The code comment explains the limit: answers from Wi-Fi are typically
accurate to tens or hundreds of metres, so a radius beyond 1000 m means the
answer came from the internet address, whatever was sent.

| Access points sent | Accuracy returned | `source` | Test |
|---|---|---|---|
| 2 | 35 m | `wifi` | `test_two_access_points_are_sent_as_wifi` |
| 1 (so none sent) | 2700 m | `ip` | `test_one_access_point_falls_back_to_internet_address` |
| 2 | 2700 m | `ip` | `test_wide_answer_is_labelled_ip_even_with_wifi` |

---

## 5. The result, caching, and the key

### 5.1 The result object

`GET /api/location` returns:

```json
{
  "status": "ok",
  "source": "wifi",
  "lat": 16.4955,
  "lng": 80.5098,
  "accuracy": 40.0,
  "access_points": 6,
  "checked_at": 1763540000.0,
  "error": null
}
```

`access_points` is the number of access points found by the scan (even if
fewer than two, so none were sent). `checked_at` is the Unix time of the
lookup.

### 5.2 Error states

| `status` | When | `error` text |
|---|---|---|
| `ok` | Google returned a location. | `null` |
| `not_configured` | No `GEOLOCATION_API_KEY` is set. No scan is made and Google is not contacted. | "Add GEOLOCATION_API_KEY to the .env file on the Pi, then restart CogniSight." |
| `error` | The request could not be sent or timed out (no internet, DNS failure). | "Could not reach Google: …" |
| `error` | Google answered with an error status or without a location (for example, an invalid key or a disabled API). | Google's own message (for example "Not Found"), or "Google could not place this device (HTTP 404)." |

Errors are returned as data with HTTP status 200, so the Place page can
explain them. The endpoint itself returns HTTP 503 "Location is not available."
only if the server was created without a locator, which happens in the tests
but not in the normal program.

### 5.3 The cache: 5 minutes for answers, 30 seconds for errors

`Locator.current(force=False)` keeps the last result. A new scan and lookup
are made only if there is no result yet, or `force` is true
(`POST /api/location/refresh`, the **Check again** button), or the last result
has expired:

| Last result | Kept for |
|---|---|
| `ok` or `not_configured` | **300 seconds (5 minutes)** (`CACHE_SECONDS = 300`) |
| `error` | **30 seconds** (`ERROR_CACHE_SECONDS = 30`), so a failed lookup (for example, while the internet connection was briefly down) is retried soon |

A lock ensures only one lookup runs at a time; a second request waits for the
first and then receives its result.

Lookups are lazy: nothing is sent to Google until someone opens the Place page
(or calls the API). The Place page asks every 60 seconds while it is visible,
but because of the cache, Google is contacted at most once every five minutes
after a successful answer, plus once per **Check again**. After an error, the
next page refresh (within about a minute) tries again. This keeps the number of
billable API calls low.

### 5.4 Key handling

- The key is read from the environment variable `GEOLOCATION_API_KEY` when the
  program starts.
- `cognisight` loads `.env` from the repository folder at start-up
  (`load_env()` in `cli.py`): each `KEY=value` line is read, blank lines and
  lines starting with `#` are ignored, an `export ` prefix and surrounding
  quotes are removed, and variables already set in the environment are **not**
  overridden.
- `setup.sh` creates `.env` from `.env.example` (which contains an empty
  `GEOLOCATION_API_KEY=`) if it does not exist.
- `.env` is listed in `.gitignore`, so the key is not committed.
- The key is used only to build the request URL on the Pi. No API response
  contains it, and the dashboard never receives it. The browser talks only to
  the Pi.
- Because the key is read once, adding or changing it requires restarting
  CogniSight, as the error message and the Place page both say.

---

## 6. The Place page

The Place page (`/place`) shows the room at home (from the talking signs; see
[signposts.md](signposts.md)) and, under "On the map", the location:

- **While loading**: "Looking up the location…", or "Waiting for the device."
  when offline.
- **Not configured**: a panel "Location isn't set up yet" explaining that a
  Google Geolocation API key is needed, with three steps: open the `.env` file
  on the Pi, add `GEOLOCATION_API_KEY=your-key`, restart CogniSight and press
  "Check again".
- **Error**: "The last location check failed. <reason> Press “Check again” to
  retry."
- **A position**:
  - a Leaflet map with OpenStreetMap tiles, a moss-green dot at the position,
    and a shaded circle with the accuracy radius; the map zooms to fit the
    circle (at most zoom level 17), or to level 16 if there is no accuracy;
  - for `wifi`: "Placed from 6 nearby Wi-Fi access points, within about 40 m.";
  - for `ip`, one of two sentences, depending on why the answer is rough:
    - if two or more access points were found (and so sent), but Google still
      answered from the internet address: "Google could not match the 6 nearby
      Wi-Fi access points, so it placed the device from its internet
      connection. This is a rough area, about 5.4 km wide.";
    - otherwise (zero or one access point): "Only the internet connection's
      location was available, so this is a rough area, about 5.4 km wide.
      Google needs at least two Wi-Fi access points in range for a closer
      fix."

    The width is twice the accuracy radius, because Google's accuracy is a
    radius: an accuracy of 2.7 km is an area about 5.4 km across. Both
    sentences are styled differently from the Wi-Fi one to mark the position as
    approximate;
  - the coordinates to five decimal places, "Within 40 m", "Checked 3 min ago",
    and a link "Open in OpenStreetMap";
  - if two map tiles fail to load: "The map can't load without an internet
    connection. The position below is still correct."
- **Check again** forces a fresh lookup. The browser allows 30 seconds both
  for this and for the page's regular reads, more than the roughly 20 seconds
  a fresh lookup can take on the device (10-second scan plus 10-second
  request).

Distances are shown as whole metres below 100 m, rounded to 10 m up to 1 km,
and in kilometres above that.

On phones, one-finger drags scroll the page rather than pan the map, and the
scroll wheel does not zoom it.

---

## 7. Privacy

- Sent to Google with each lookup: the hardware addresses (BSSIDs), signal
  strengths, and channels of the nearby access points, including neighbours'
  networks, and, implicitly, the Pi's public internet address. Nothing about
  the wearer, faces, or photos is sent.
- The caregiver's browser loads map tiles for the area around the position from
  `tile.openstreetmap.org`, which therefore learns the approximate area being
  viewed.
- Results are kept only in memory on the Pi.

---

## 8. Limitations

- **Untested on the Pi.** `nmcli` output and permissions for scanning on
  Raspberry Pi OS have not been checked under this program.
- **Needs internet and a Google key with billing.** Google requires a billing
  account even for the free allowance; the project overview describes the
  difficulty of setting this up from India.
- **Few access points means a rough answer.** Where only one access point is
  visible (as in the hostel where the project was developed), only the
  internet-address estimate is available: an accuracy radius of kilometres,
  for example about 2.7 km, which is an area about 5.4 km across.
- **A scan failure is silent.** If `nmcli` is missing or fails, the result is
  simply labelled `ip` with `access_points` 0; no scan error is shown.
- **A slow scan is cut short.** The 10-second scan limit is untested on the Pi;
  if `nmcli` needs longer to rescan, the lookup proceeds with no access points
  and falls back to the internet address.
