"""Verify portable benchmark is opt-in and does not masquerade as DAW CPU %."""
from pathlib import Path
import unittest

BASE=Path(__file__).resolve().parents[1]

class SkellNativeBenchmarkConfigTests(unittest.TestCase):
    def test_opt_in_and_no_juce_in_benchmark(self):
        cmake=(BASE/"native/CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn('option(SKELLNATIVE_BUILD_BENCHMARKS',cmake)
        self.assertIn('add_executable(SkellNativeBenchmark',cmake)
        self.assertIn('SkellNativeBenchmarkSmoke',cmake)
        benchmark=(BASE/"native/benchmarks/benchmark_dsp.cpp").read_text(encoding="utf-8")
        for token in ("44100.0","48000.0","96000.0",
                      "64,256,1024","steady_clock","trials=5",
                      "gain_peak","ns_per_frame_per_channel"):
            self.assertIn(token,benchmark)
        self.assertNotIn("#include <juce",benchmark)
        self.assertNotIn("#include \"pluginterfaces/",benchmark)
        self.assertIn("not FL Studio CPU %",benchmark)

    def test_field_results_are_clearly_user_reported(self):
        doc=(BASE/"docs/SKELLNATIVE_BENCHMARKS.md").read_text(encoding="utf-8")
        self.assertIn("user-reported acceptance observations",doc)
        self.assertIn("not automated FL Studio",doc)
        self.assertIn("NOT FL Studio CPU %",doc)
        self.assertIn("Three instances",doc)

if __name__=="__main__":
    unittest.main()
