"""Threshold selection and held-out evaluation tests; fixtures are synthetic."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.evaluate_recognition import evaluate, write_report


def fixture(kind="synthetic"):
    return {
        "data_kind": kind,
        "model_version": "test-sface-v1",
        "gallery": {"a": [[1, 0]], "b": [[0, 1]]},
        "calibration": [
            {"encounter_id": "c-a", "expected": "a", "embedding": [1, 0]},
            {"encounter_id": "c-u", "expected": None, "embedding": [-1, -1]},
        ],
        "evaluation": [
            {"encounter_id": "e-a", "expected": "a", "embedding": [1, 0]},
            {"encounter_id": "e-u", "expected": None, "embedding": [-1, -1]},
        ],
    }


class EvaluationTests(unittest.TestCase):
    def test_calibration_never_reads_evaluation_when_selecting_threshold(self):
        data = fixture()
        original = evaluate(data)
        data["evaluation"][1]["embedding"] = [1, 0]
        changed = evaluate(data)
        self.assertEqual(original["selection"], changed["selection"])
        self.assertEqual(original["evaluation"]["unknown_false_named"], 0)
        self.assertEqual(changed["evaluation"]["unknown_false_named"], 1)
        self.assertFalse(changed["accuracy_qualified"])

    def test_named_error_and_known_rejection_count_separately(self):
        data = fixture()
        data["evaluation"] = [
            {"encounter_id": "e-wrong", "expected": "a", "embedding": [0, 1]},
            {"encounter_id": "e-reject", "expected": "a", "embedding": [-1, -1]},
        ]
        stats = evaluate(data)["evaluation"]
        self.assertEqual(stats["known_total"], 2)
        self.assertEqual(stats["known_wrong_named"], 1)
        self.assertEqual(stats["known_rejected"], 1)
        self.assertEqual(stats["known_correct_rate"], 0.0)

    def test_qualified_only_with_real_metadata_and_required_evaluation_counts(self):
        data = fixture("consented_real")
        data["evaluation"] = [
            {"encounter_id": "known-" + str(i), "expected": "a", "embedding": [1, 0]}
            for i in range(20)
        ] + [
            {"encounter_id": "unknown-" + str(i), "expected": None, "embedding": [-1, -1]}
            for i in range(300)
        ]
        report = evaluate(data)
        self.assertTrue(report["accuracy_qualified"])
        self.assertEqual(report["coverage"]["evaluated_known_people"], 1)
        self.assertFalse(report["coverage"]["all_gallery_people_evaluated"])
        self.assertFalse(report["coverage"]["hundred_real_person_gallery_evaluated"])
        data["data_kind"] = "synthetic"
        self.assertFalse(evaluate(data)["accuracy_qualified"])
        data["data_kind"] = "consented_real"
        data["evaluation"].pop()
        self.assertFalse(evaluate(data)["accuracy_qualified"])

    def test_rejects_leakage_bad_dimensions_nonfinite_and_unknown_expected(self):
        changes = [
            lambda d: d["evaluation"][0].update(encounter_id="c-a"),
            lambda d: d["evaluation"][0].update(embedding=[1, 0, 0]),
            lambda d: d["evaluation"][0].update(embedding=[float("nan"), 0]),
            lambda d: d["evaluation"][0].update(embedding=[0, 0]),
            lambda d: d["evaluation"][0].update(expected="not-enrolled"),
            lambda d: d["gallery"].update(a=[]),
            lambda d: d.update(calibration=[d["calibration"][0]]),
            lambda d: d.update(data_kind="unknown"),
        ]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                data = fixture()
                change(data)
                with self.assertRaises(ValueError):
                    evaluate(data)

    def test_rejects_no_safe_calibration_setting_and_gallery_over_capacity(self):
        data = fixture()
        data["calibration"][1]["embedding"] = [1, 0]
        with self.assertRaises(ValueError):
            evaluate(data)
        data = fixture()
        data["gallery"] = {str(i): [[1, 0]] for i in range(101)}
        with self.assertRaises(ValueError):
            evaluate(data)

    def test_report_has_no_embedding_person_id_or_encounter_id_and_is_private(self):
        report = evaluate(fixture())
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "report.json"
            write_report(destination, report)
            text = destination.read_text()
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
            self.assertNotIn("embedding", text)
            self.assertNotIn("c-a", text)
            self.assertNotIn('"expected"', text)
            self.assertEqual(json.loads(text)["model_version"], "test-sface-v1")


if __name__ == "__main__":
    unittest.main()
