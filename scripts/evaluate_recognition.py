#!/usr/bin/env python3
"""Select thresholds on calibration encounters; evaluate a disjoint held-out set.

Run from the repository with PYTHONPATH=src, or after installing cognisight.
The input is PRIVATE biometric test data, never a repository fixture. Unique
encounter IDs and data_kind are caller assertions, not proof of independence,
consent, or real-world representativeness. This tool cannot certify those facts.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import tempfile

from cognisight.recognition.matching import Gallery


THRESHOLDS = tuple(round(0.30 + 0.02 * i, 2) for i in range(31))
MARGINS = (0.02, 0.05, 0.10, 0.15)


def _vector(value, dimension=None):
    if (
        not isinstance(value, list)
        or not value
        or any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in value)
        or not all(math.isfinite(x) for x in value)
    ):
        raise ValueError("All feature vectors must be nonempty finite numeric arrays")
    norm = math.sqrt(sum(x * x for x in value))
    if not math.isfinite(norm) or norm < 1e-12:
        raise ValueError("Feature vector norm must be finite and nonzero")
    if dimension is not None and len(value) != dimension:
        raise ValueError("All feature vectors must have the same dimensions")
    return tuple(x / norm for x in value)


def _validate(data):
    if not isinstance(data, dict):
        raise ValueError("Input must be an object")
    if data.get("data_kind") not in ("consented_real", "synthetic"):
        raise ValueError("data_kind must be consented_real or synthetic")
    if not isinstance(data.get("model_version"), str) or not data["model_version"].strip():
        raise ValueError("A nonempty model_version is required")
    people = data.get("gallery")
    if not isinstance(people, dict) or not 1 <= len(people) <= 100:
        raise ValueError("Gallery must contain between one and 100 people")
    gallery = {}
    dimension = None
    for person, values in people.items():
        if (
            not isinstance(person, str)
            or not person.strip()
            or not isinstance(values, list)
            or not values
        ):
            raise ValueError("Each gallery person requires an ID and at least one sample")
        samples = []
        for value in values:
            sample = _vector(value, dimension)
            dimension = len(sample)
            samples.append(sample)
        gallery[person] = samples
    seen = set()
    splits = {}
    for split in ("calibration", "evaluation"):
        rows = data.get(split)
        if not isinstance(rows, list) or not rows:
            raise ValueError("Both calibration and evaluation require encounters")
        checked = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Each encounter must be an object")
            encounter = row.get("encounter_id")
            if not isinstance(encounter, str) or not encounter.strip() or encounter in seen:
                raise ValueError("Encounter IDs must be nonempty and unique across both splits")
            seen.add(encounter)
            if "expected" not in row:
                raise ValueError("Encounter expected identity is required; null means unknown")
            expected = row["expected"]
            if expected is not None and (not isinstance(expected, str) or expected not in gallery):
                raise ValueError("Expected identity must be enrolled or null")
            checked.append((expected, _vector(row.get("embedding"), dimension)))
        splits[split] = checked
    calibration_known = sum(expected is not None for expected, _ in splits["calibration"])
    if not 0 < calibration_known < len(splits["calibration"]):
        raise ValueError("Calibration requires at least one known and one unknown encounter")
    return gallery, splits


def _measure(gallery, rows):
    stats = {
        "encounters_total": len(rows),
        "known_total": 0,
        "unknown_total": 0,
        "known_correct": 0,
        "known_wrong_named": 0,
        "known_rejected": 0,
        "unknown_false_named": 0,
    }
    for expected, vector in rows:
        result = gallery.match(vector)
        if expected is None:
            stats["unknown_total"] += 1
            stats["unknown_false_named"] += result.person_id is not None
        else:
            stats["known_total"] += 1
            if result.person_id == expected:
                stats["known_correct"] += 1
            elif result.person_id is not None:
                stats["known_wrong_named"] += 1
            else:
                stats["known_rejected"] += 1
    stats["known_correct_rate"] = (
        stats["known_correct"] / stats["known_total"] if stats["known_total"] else None
    )
    stats["unknown_false_named_rate"] = (
        stats["unknown_false_named"] / stats["unknown_total"] if stats["unknown_total"] else None
    )
    # Exact one-sided 95% upper bound only for the zero-error binomial case.
    stats["unknown_error_upper_95_if_independent"] = (
        1 - 0.05 ** (1 / stats["unknown_total"])
        if stats["unknown_total"] and not stats["unknown_false_named"]
        else None
    )
    return stats


def evaluate(data):
    """Return aggregate-only results; never tune against evaluation labels."""
    people, splits = _validate(data)
    best = None
    for threshold in THRESHOLDS:
        for margin in MARGINS:
            gallery = Gallery(people, threshold=threshold, margin=margin)
            stats = _measure(gallery, splits["calibration"])
            if stats["unknown_false_named"] or stats["known_wrong_named"]:
                continue
            # Maximize correct known encounters, then prefer stricter decisions
            # on ties. Rejected calibration encounters are NOT counted correct.
            rank = (stats["known_correct"], threshold, margin)
            if best is None or rank > best[0]:
                best = (rank, threshold, margin, stats)
    if best is None:
        raise ValueError("No grid setting avoids calibration false named matches")
    _, threshold, margin, calibration = best
    stats = _measure(Gallery(people, threshold, margin), splits["evaluation"])
    known_people = {expected for expected, _ in splits["evaluation"] if expected is not None}
    qualified = (
        data["data_kind"] == "consented_real"
        and stats["known_total"] >= 20
        and stats["unknown_total"] >= 300
        and stats["known_correct_rate"] >= 0.95
        and stats["known_wrong_named"] == 0
        and stats["unknown_false_named"] == 0
    )
    return {
        "schema_version": 1,
        "model_version": data["model_version"],
        "data_kind": data["data_kind"],
        "selection": {"threshold": threshold, "margin": margin},
        "calibration": calibration,
        "evaluation": stats,
        "accuracy_qualified": qualified,
        "qualification_scope": "evaluated_cohort_only",
        "coverage": {
            "gallery_people": len(people),
            "evaluated_known_people": len(known_people),
            "all_gallery_people_evaluated": len(known_people) == len(people),
            "hundred_real_person_gallery_evaluated": (
                data["data_kind"] == "consented_real"
                and len(people) == 100
                and len(known_people) == 100
            ),
        },
        "assumptions": [
            "Data source, consent and encounter independence are supplied assertions, not verified facts.",
            "Accuracy applies only to the evaluated cohort and conditions; this is not hardware qualification.",
            "Synthetic input can verify software/load behavior but cannot qualify biological recognition accuracy.",
            "Calibration does not modify runtime configuration; review held-out results before applying thresholds.",
        ],
    }


def write_report(destination, report):
    """Write a mode-0600 JSON report atomically without following target links."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix=".recognition-report-", dir=str(destination.parent))
    try:
        with os.fdopen(descriptor, "w") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(report, handle, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, destination)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON object keys are not permitted")
        value[key] = item
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Private calibration/evaluation JSON file")
    parser.add_argument(
        "--output", required=True, type=Path, help="Private aggregate report destination"
    )
    args = parser.parse_args(argv)
    try:
        if args.input.resolve() == args.output.resolve():
            raise ValueError("Output must not overwrite source data")
        with args.input.open() as handle:
            data = json.load(handle, object_pairs_hook=_unique_object)
        report = evaluate(data)
        write_report(args.output, report)
    except (ValueError, OSError, TypeError, OverflowError) as error:
        # Do not print private input content or person/encounter identifiers.
        parser.exit(
            2,
            "Evaluation failed: "
            + type(error).__name__
            + ". Check input schema and access permissions.\n",
        )
    print(
        json.dumps(
            {
                "report_written": True,
                "accuracy_qualified": report["accuracy_qualified"],
                "qualification_scope": report["qualification_scope"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
