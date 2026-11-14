"""Validate user-provided Ryzen benchmark transcription and summary."""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from tools.summarize_gain_compare import analyze, REQUIRED

BASE = (Path(__file__).resolve().parents[1]
        / "native/benchmarks/juce_compare/results/user_ryzen_2026-11-13.csv")


class RyzenBenchmarkTests(unittest.TestCase):
    def test_user_results_are_complete_and_consistent(self):
        report = analyze(BASE)
        self.assertEqual(report["cases"], 9)
        self.assertEqual(report["native_faster_cases"], 9)
        self.assertEqual(report["max_error_reported"], 0.0)
        self.assertAlmostEqual(report["median_native_to_juce"], 0.4846, delta=0.0001)
        self.assertAlmostEqual(report["median_old_to_native"], 4.7356, delta=0.0001)

    def test_missing_and_duplicate_cases_rejected(self):
        with BASE.open(encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        for changed in (rows[:-1], rows[:-1] + rows[0:1]):
            with tempfile.TemporaryDirectory() as tmp:
                file = Path(tmp) / "bad.csv"
                with file.open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=REQUIRED)
                    writer.writeheader()
                    writer.writerows(changed)
                with self.assertRaises(ValueError):
                    analyze(file)

    def test_docs_mark_manual_measurement_and_limitations(self):
        docs = (Path(__file__).resolve().parents[1]
                / "docs/SKELLNATIVE_RYZEN_BASELINE_2026-11-13.md").read_text()
        self.assertIn("manual transcription", docs)
        self.assertIn("isolated DSP loop", docs)
        self.assertIn("host overhead", docs)
        self.assertIn("2.06x faster", docs)


if __name__ == "__main__":
    unittest.main()
