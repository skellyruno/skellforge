"""Guard optional fused gain/output meter and protected plugin IDs."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class FusedMeterTests(unittest.TestCase):
    def test_fused_kernel_and_exact_audio_parity(self):
        gain=(ROOT/"native/include/SkellNative/Dsp.h").read_text(encoding="utf-8")
        proc=(ROOT/"native/vst3/Source/NativeGainProcessor.cpp").read_text(encoding="utf-8")
        suite=(ROOT/"native/tests/test_native_dsp.cpp").read_text(encoding="utf-8")
        self.assertIn("processWithPeak(Block block, float& outputPeak)",gain)
        self.assertIn("_mm_max_ps(peak4, _mm_min_ps(amplitude, clip))",gain)
        self.assertIn("if (!capturePeak) return kernel_.process(block);",proc)
        self.assertIn("kernel_.processWithPeak(block,spanPeak)",proc)
        self.assertIn("No extra full-buffer memory scan",proc)
        self.assertIn("testFusedGainOutputMeterParity",suite)
        self.assertIn("std::memcmp(&x,&y,sizeof(float))",suite)
        self.assertIn("SKELLNATIVE_DISABLE_SIMD=1",
                      (ROOT/"native/CMakeLists.txt").read_text(encoding="utf-8"))
    def test_gain_state_and_parameter_ids_unchanged(self):
        ids=(ROOT/"native/vst3/Source/NativeGainIDs.h").read_text(encoding="utf-8")
        bridge=(ROOT/"native/vst3/Source/NativeGainStateBridge.h").read_text(encoding="utf-8")
        self.assertIn("kGainParam = 1000u",ids)
        self.assertIn("kOutputPeakParam = 1001u",ids)
        self.assertIn("writeNormalizedGain",bridge)
        self.assertIn("readNormalizedGain",bridge)
if __name__=="__main__":
    unittest.main()
