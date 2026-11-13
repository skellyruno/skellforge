"""Check paired local gain benchmark, no native JUCE dependency on Linux."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"native/benchmarks/juce_compare"
class JuceGainCompareTests(unittest.TestCase):
    def test_source_matches_and_checks_signal_parity(self):
        source=(BASE/"compare_gain.cpp").read_text(encoding="utf-8")
        cmake=(BASE/"CMakeLists.txt").read_text(encoding="utf-8")
        for snippet in ("#include <juce_dsp/juce_dsp.h>",
                        "#include <SkellNative/Dsp.h>","juceGain(",
                        "native(Stereo&","1.0e-5","44100.","48000.","96000."):
            self.assertIn(snippet,source)
        self.assertIn("GIT_TAG 8.0.12",cmake)
        self.assertIn("juce::juce_dsp",cmake)
        self.assertIn("/O2",cmake)
    def test_local_script_never_installs_plugins(self):
        script=(BASE/"Run-GainCompare.ps1").read_text(encoding="utf-8")
        self.assertIn("--parallel 2",script)
        self.assertIn("Import-Csv",script)
        self.assertNotIn("Remove-Item",script)
        self.assertNotIn("Common Files",script)
        self.assertIn("DSP",script)
if __name__=="__main__":
    unittest.main()
