"""Allowlisted monitoring projection; absent or invalid input never becomes live."""

import math
from datetime import datetime
import re

SOURCES = {"live", "mock", "unavailable"}
HEALTH = {
    "camera",
    "microphone",
    "playback",
    "model",
    "storage",
    "clock",
    "runtime",
    "gpsd",
    "navigation",
}
STATUSES = {
    "live",
    "unavailable",
    "stale",
    "paused",
    "uncalibrated",
    "no_fix",
    "disconnected",
    "invalid",
    "mock",
    "starting",
}


def number(value, low=0, high=float("inf")):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value if low <= value <= high else None


def timestamp(value):
    if isinstance(value, str):
        try:
            instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if instant.tzinfo is None:
                return None
            value = instant.timestamp()
        except (ValueError, OverflowError, OSError):
            return None
    return number(value, 0, 253402300799)


def text(value, limit):
    return value[:limit] if isinstance(value, str) else ""


def reason(value, fallback="not_integrated"):
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9_:-]{1,64}", value)
        else fallback
    )


def _base(raw, inherited, expiry):
    raw = raw if isinstance(raw, dict) else {}
    source = raw.get("data_source", inherited)
    source = source if isinstance(source, str) and source in SOURCES else "unavailable"
    status = raw.get("status", "unavailable")
    status = status if isinstance(status, str) and status in STATUSES else "unavailable"
    requested_expiry = number(raw.get("max_age_seconds"), 0, 300)
    if requested_expiry is not None and requested_expiry > 0:
        expiry = requested_expiry
    age = number(raw.get("age_seconds"))
    if source == "unavailable" and status == "live":
        status = "unavailable"
    elif source == "mock":
        status = "mock"
    elif status == "live" and (age is None or age >= expiry):
        status = "stale"
    return {
        "status": status,
        "data_source": source,
        "age_seconds": age,
        "observed_at": timestamp(raw.get("observed_at")),
        "reason": reason(raw.get("reason"), "unknown_age" if age is None else status),
        "max_age_seconds": expiry,
    }


def _fix(raw):
    if not isinstance(raw, dict):
        return None
    latitude = number(raw.get("latitude"), -90, 90)
    longitude = number(raw.get("longitude"), -180, 180)
    if latitude is None or longitude is None:
        return None
    return {
        "latitude": latitude,
        "longitude": longitude,
        "observed_at": timestamp(raw.get("observed_at")),
        "age_seconds": number(raw.get("age_seconds")),
        "label": "Last known location",
    }


def collect_snapshot(raw):
    raw = raw if isinstance(raw, dict) and raw.get("schema_version") == 1 else {}
    inherited = raw.get("data_source", "unavailable")
    recognition_raw = raw.get("recognition") if isinstance(raw.get("recognition"), dict) else {}
    recognition = _base(recognition_raw, inherited, 1)
    recognition["people"] = []
    if recognition["status"] in ("live", "mock"):
        people = recognition_raw.get("people", [])
        for person in (people[:4] if isinstance(people, list) else []):
            if (
                not isinstance(person, dict)
                or not text(person.get("person_id"), 100)
                or not text(person.get("name"), 100)
            ):
                continue
            recognition["people"].append(
                {
                    key: text(person.get(key), limit)
                    for key, limit in (
                        ("person_id", 100),
                        ("name", 100),
                        ("relationship", 150),
                        ("note", 500),
                    )
                }
            )
    outdoor_raw = raw.get("outdoor") if isinstance(raw.get("outdoor"), dict) else {}
    outdoor = _base(outdoor_raw, inherited, 10)
    outdoor.update(
        latitude=None,
        longitude=None,
        speed_mps=None,
        source=reason(outdoor_raw.get("source"), "unknown"),
    )
    fix = _fix(outdoor_raw)
    if outdoor["status"] in ("live", "mock"):
        if fix:
            outdoor.update(
                latitude=fix["latitude"],
                longitude=fix["longitude"],
                speed_mps=number(outdoor_raw.get("speed_mps")),
            )
        else:
            outdoor["status"] = "invalid"
            outdoor["reason"] = "invalid_coordinates"
    outdoor["last_known"] = _fix(outdoor_raw.get("last_known", outdoor_raw.get("last_valid")))
    indoor_raw = raw.get("indoor") if isinstance(raw.get("indoor"), dict) else {}
    indoor = _base(indoor_raw, inherited, 10)
    # No implemented indoor producer/contract yet: never infer navigation state.
    indoor.update(status="unavailable", reason="not_integrated", data_source="unavailable")
    raw_health = raw.get("health") if isinstance(raw.get("health"), dict) else {}
    health = {key: reason(value, "unknown") for key, value in raw_health.items() if key in HEALTH}
    return {
        "schema_version": 1,
        "recognition": recognition,
        "outdoor": outdoor,
        "indoor": indoor,
        "health": health,
        "has_mock_data": any(
            item["data_source"] == "mock" for item in (recognition, outdoor, indoor)
        ),
    }
