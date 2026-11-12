"""Bounded local GPSD client with explicit current/last-known fix semantics.

No receiver commands, route calculation, position recording or network GPSD
publication occurs here. Complete TPV reports are the only source of fixes.
"""

import json
import math
import socket
import threading
import time
from datetime import datetime, timezone

MAX_LINE = 10240


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Expected a finite number")
    return float(value)


def _utc(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("GNSS UTC must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or not 2020 <= parsed.year <= 2100:
        raise ValueError("GNSS UTC must have timezone and plausible date")
    return parsed.astimezone(timezone.utc).isoformat()


class NavigationService:
    """One local GPSD consumer. Public snapshots are safe JSON dictionaries.

    `observed_at` is receiver UTC, never a substituted wall clock. Freshness is
    measured using reception monotonic time. `last_known` is historical even
    while the source is disconnected, invalid, no-fix or stale.
    """

    def __init__(self, config, on_update=None, *, clock=time.monotonic):
        self.host = config.get("gpsd_host", "127.0.0.1")
        self.port = config.get("gpsd_port", 2947)
        self.max_age = _number(config.get("fix_max_age", 10))
        if self.host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("GPSD must be local; do not expose location daemon on the LAN")
        if (
            isinstance(self.port, bool)
            or not isinstance(self.port, int)
            or not 1 <= self.port <= 65535
        ):
            raise ValueError("Invalid GPSD port")
        if not 0 < self.max_age <= 300:
            raise ValueError("fix_max_age must be positive and no more than 300 seconds")
        self.on_update = on_update
        self.clock = clock
        self.lock = threading.RLock()
        self._route_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._socket = None
        self._status = "disconnected"
        self._reason = "not_started"
        self._last = None
        self._protocol_ready = False
        self._last_emitted = None
        self._device = None

    def _state(self, status, reason):
        with self.lock:
            self._status, self._reason = status, reason
        self._notify()

    def snapshot(self, now=None):
        now = self.clock() if now is None else _number(now)
        with self.lock:
            status, reason = self._status, self._reason
            historical = None
            if self._last:
                age = max(0.0, now - self._last["received_at"])
                historical = {
                    key: value for key, value in self._last.items() if key != "received_at"
                }
                historical["age_seconds"] = age
                if status == "live" and age >= self.max_age:
                    status, reason = "stale", "fix_expired"
            else:
                age = None
            current = historical if status == "live" else None
            return {
                "schema_version": 1,
                "status": status,
                "reason": reason,
                "latitude": current["latitude"] if current else None,
                "longitude": current["longitude"] if current else None,
                "observed_at": current["observed_at"] if current else None,
                "speed_mps": current["speed_mps"] if current else None,
                "age_seconds": age,
                "max_age_seconds": self.max_age,
                "source": "gpsd",
                "data_kind": "live",
                "data_source": "live" if status == "live" else "unavailable",
                "last_known": historical,
                "navigation": {"status": "unavailable", "reason": "route_provider_not_configured"},
            }

    def _notify(self):
        if self.on_update is None:
            return
        snapshot = self.snapshot()
        with self.lock:
            if snapshot == self._last_emitted:
                return
            self._last_emitted = snapshot
        try:
            self.on_update(snapshot)
        except Exception:
            # A consumer failure must not stop GNSS reception or log positions.
            pass

    def accept_report(self, report):
        """Validate a decoded GPSD report; used by the socket adapter."""
        if not isinstance(report, dict):
            self._state("invalid", "malformed_report")
            return
        if report.get("class") != "TPV":
            return
        mode = report.get("mode")
        if isinstance(mode, bool) or not isinstance(mode, int) or mode not in (0, 1, 2, 3):
            self._state("invalid", "invalid_fix_mode")
            return
        if mode < 2:
            self._state("no_fix", "receiver_has_no_fix")
            return
        # GPSD may send several partial messages per epoch. Never merge unrelated
        # epochs or let a speed-only report keep old coordinates falsely fresh.
        if "lat" not in report or "lon" not in report:
            self._notify()
            return
        try:
            latitude, longitude = _number(report["lat"]), _number(report["lon"])
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise ValueError("Coordinates out of range")
            observed = _utc(report.get("time"))
            speed = _number(report["speed"]) if "speed" in report else None
            if speed is not None and speed < 0:
                raise ValueError("Negative speed")
            device = report.get("device")
            if device is not None and not isinstance(device, str):
                raise ValueError("Invalid source device")
        except (ValueError, TypeError, OverflowError):
            self._state("invalid", "invalid_fix_fields")
            return
        with self.lock:
            if self._device is not None and device is not None and device != self._device:
                self._status, self._reason = "invalid", "multiple_receivers"
            elif (
                observed is not None
                and self._last
                and self._last["observed_at"] is not None
                and datetime.fromisoformat(observed)
                <= datetime.fromisoformat(self._last["observed_at"])
            ):
                if datetime.fromisoformat(observed) < datetime.fromisoformat(
                    self._last["observed_at"]
                ):
                    self._status, self._reason = "invalid", "out_of_order_epoch"
                # An identical epoch is another partial/duplicate TPV, not new
                # position evidence. Preserve its original receive age.
            else:
                if device is not None:
                    self._device = device
                self._last = {
                    "latitude": latitude,
                    "longitude": longitude,
                    "observed_at": observed,
                    "speed_mps": speed,
                    "received_at": self.clock(),
                }
                self._status, self._reason = "live", "valid_fix"
        self._notify()

    def accept_line(self, line):
        if len(line) > MAX_LINE:
            self._state("invalid", "oversized_report")
            raise ValueError("GPSD report exceeds bounded line size")

        def invalid_constant(value):
            raise ValueError("Nonfinite JSON constant")

        try:
            report = json.loads(line, parse_constant=invalid_constant)
            if not isinstance(report, dict):
                raise ValueError("GPSD report must be an object")
        except (ValueError, TypeError, UnicodeError):
            self._state("invalid", "malformed_report")
            raise ValueError("Malformed GPSD JSON") from None
        if report.get("class") == "VERSION":
            if type(report.get("proto_major")) is not int or report["proto_major"] != 3:
                self._state("invalid", "unsupported_protocol")
                raise ValueError("Unsupported GPSD protocol major")
            self._protocol_ready = True
            self._state("no_fix", "waiting_for_fix")
            return
        if not self._protocol_ready:
            self._state("invalid", "missing_protocol_banner")
            raise ValueError("GPSD VERSION banner required")
        if report.get("class") == "ERROR":
            self._state("invalid", "gpsd_error")
            return
        self.accept_report(report)

    def start(self):
        with self.lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="outdoor-gpsd", daemon=True)
            self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                connection = socket.create_connection((self.host, self.port), timeout=1)
                connection.settimeout(1)
                with self._route_lock:
                    if self._stop.is_set():
                        connection.close()
                        break
                    self._socket = connection
                self._protocol_ready = False
                self._device = None
                self._state("no_fix", "waiting_for_fix")
                connection.sendall(b'?WATCH={"enable":true,"json":true};\n')
                buffer = b""
                while not self._stop.is_set():
                    try:
                        chunk = connection.recv(4096)
                    except socket.timeout:
                        self._notify()
                        continue
                    if not chunk:
                        raise ConnectionError("GPSD disconnected")
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        if line.strip():
                            self.accept_line(line)
                    if len(buffer) > MAX_LINE:
                        self._state("invalid", "oversized_report")
                        raise ValueError("GPSD report exceeds bounded line size")
            except (OSError, ValueError):
                if not self._stop.is_set():
                    self._state("disconnected", "gpsd_connection_lost")
            finally:
                with self._route_lock:
                    old, self._socket = self._socket, None
                    if old:
                        try:
                            old.close()
                        except OSError:
                            pass
            self._stop.wait(5)
        self._state("disconnected", "stopped")

    def close(self):
        self._stop.set()
        with self._route_lock:
            connection = self._socket
            if connection is not None:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    connection.close()
                except OSError:
                    pass
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2)
        self._state("disconnected", "stopped")
