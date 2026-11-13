"""Validate and summarize local JUCE/SkellNative gain measurements.

Reports median per-case time ratios, not total DAW CPU or latency.
Standard library only. No hardware access and no network.
"""
from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path

REQUIRED = (
    "rate_hz", "block_frames", "native_ms", "juce_ms",
    "native_over_juce", "max_error",
    "old_scalar_ms", "old_scalar_over_native",
)
EXPECTED = {(rate, count) for rate in (44100, 48000, 96000)
            for count in (64, 256, 1024)}


def analyze(path: Path) -> dict:
    """Return verified data summary; fail closed on incomplete CSV."""
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or tuple(reader.fieldnames) != REQUIRED:
            raise ValueError("Unexpected columns; expected eight current benchmark columns")
        entries = list(reader)
    seen = set()
    native_to_juce = []
    old_to_native = []
    max_errors = []
    for entry in entries:
        try:
            key = (int(entry["rate_hz"]), int(entry["block_frames"]))
            values = {field: float(entry[field]) for field in REQUIRED[2:]}
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"Bad benchmark data in row {len(seen) + 1}") from exc
        if key not in EXPECTED or key in seen:
            raise ValueError(f"Invalid or repeated rate/buffer combination: {key}")
        seen.add(key)
        if (not all(math.isfinite(value) for value in values.values())
                or min(values["native_ms"], values["juce_ms"],
                       values["old_scalar_ms"]) <= 0
                or values["max_error"] < 0):
            raise ValueError(f"Nonfinite or nonpositive timing at {key}")
        # Printed columns are rounded; use measured milliseconds as source.
        native_ratio = values["native_ms"] / values["juce_ms"]
        scalar_ratio = values["old_scalar_ms"] / values["native_ms"]
        if abs(native_ratio - values["native_over_juce"]) > 0.00015:
            raise ValueError(f"Native/JUCE ratio inconsistent at {key}")
        if abs(scalar_ratio - values["old_scalar_over_native"]) > 0.0002:
            raise ValueError(f"Original/native ratio inconsistent at {key}")
        native_to_juce.append(native_ratio)
        old_to_native.append(scalar_ratio)
        max_errors.append(values["max_error"])
    if seen != EXPECTED:
        raise ValueError(f"Expected nine configurations; got {len(seen)}")
    return {
        "cases": len(seen),
        "median_native_to_juce": statistics.median(native_to_juce),
        "median_old_to_native": statistics.median(old_to_native),
        "native_faster_cases": sum(r < 1.0 for r in native_to_juce),
        "max_error_reported": max(max_errors),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path)
    args = parser.parse_args()
    try:
        values = analyze(args.csv_file)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Invalid gain benchmark: {exc}\n")
    print(f"Cases: {values['cases']}")
    print(f"Optimized native faster than JUCE: {values['native_faster_cases']}/9")
    print(f"Median native/JUCE processing time: {values['median_native_to_juce']:.4f}x")
    print(f"Median old/optimized processing time: {values['median_old_to_native']:.4f}x")
    print(f"Max printed audio error: {values['max_error_reported']:.9f}")
    print("DSP-only times; not complete FL Studio plugin CPU performance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
