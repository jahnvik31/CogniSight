"""Approximate location from nearby Wi-Fi, through Google's Geolocation API.

The Pi lists every access point it can hear with ``nmcli``; it does not need
to be connected to them. Google uses Wi-Fi only when at least two access
points are sent. Otherwise it falls back to the internet address, which is
usually kilometres away. The result says which happened, and the key never
leaves the Pi.
"""

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request

ENDPOINT = "https://www.googleapis.com/geolocation/v1/geolocate?key={}"
CACHE_SECONDS = 300
ERROR_CACHE_SECONDS = 30  # retry a failed lookup sooner
# Google answers from Wi-Fi in tens to hundreds of metres. Past this radius
# the answer came from the internet address, whatever we sent.
WIFI_ACCURACY_LIMIT = 1000.0


def parse_nmcli(text):
    """Parse ``nmcli -t -f BSSID,SIGNAL,CHAN dev wifi list``.

    In terse mode colons inside the BSSID are escaped as ``\\:``.
    """
    points = {}
    for line in (text or "").splitlines():
        fields, current, escaped = [], "", False
        for char in line.strip():
            if escaped:
                current += char
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == ":":
                fields.append(current)
                current = ""
            else:
                current += char
        fields.append(current)
        if len(fields) < 2:
            continue
        bssid = fields[0].strip().lower()
        if len(bssid) != 17 or bssid.count(":") != 5:
            continue
        try:
            signal = int(fields[1])
        except ValueError:
            continue
        point = {"macAddress": bssid, "signalStrength": round(signal / 2 - 100)}
        if len(fields) > 2 and fields[2].strip().isdigit():
            point["channel"] = int(fields[2])
        if bssid not in points or points[bssid]["signalStrength"] < point["signalStrength"]:
            points[bssid] = point
    return list(points.values())


def scan_wifi():
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "BSSID,SIGNAL,CHAN", "dev", "wifi", "list", "--rescan", "auto"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_nmcli(result.stdout)


def post_json(url, body):
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode() or "{}")
        except ValueError:
            return exc.code, {}


def lookup(key, points, post=post_json, clock=time.time):
    result = {
        "status": "error",
        "source": None,
        "lat": None,
        "lng": None,
        "accuracy": None,
        "access_points": len(points),
        "checked_at": clock(),
        "error": None,
    }
    if not key:
        result["status"] = "not_configured"
        result["error"] = "Add GEOLOCATION_API_KEY to the .env file on the Pi, then restart CogniSight."
        return result
    body = {"considerIp": True}
    if len(points) >= 2:
        body["wifiAccessPoints"] = points
    try:
        status, data = post(ENDPOINT.format(key), body)
    except (OSError, ValueError) as exc:
        result["error"] = "Could not reach Google: {}".format(exc)
        return result
    if status != 200 or "location" not in data:
        message = (data.get("error") or {}).get("message") if isinstance(data, dict) else None
        result["error"] = message or "Google could not place this device (HTTP {}).".format(status)
        return result
    accuracy = float(data.get("accuracy") or 0)
    result.update(
        status="ok",
        lat=float(data["location"]["lat"]),
        lng=float(data["location"]["lng"]),
        accuracy=accuracy,
        source="wifi" if len(points) >= 2 and accuracy <= WIFI_ACCURACY_LIMIT else "ip",
    )
    return result


class Locator:
    def __init__(self, key=None, scan=scan_wifi, post=post_json, clock=time.time):
        self.key = key if key is not None else os.environ.get("GEOLOCATION_API_KEY", "")
        self._scan = scan
        self._post = post
        self._clock = clock
        self._last = None
        self._lock = threading.Lock()

    def current(self, force=False):
        with self._lock:
            keep = CACHE_SECONDS if self._last and self._last["status"] != "error" else ERROR_CACHE_SECONDS
            fresh = self._last and self._clock() - self._last["checked_at"] < keep
            if force or not fresh:
                points = self._scan() if self.key else []
                self._last = lookup(self.key, points, self._post, self._clock)
            return dict(self._last)
