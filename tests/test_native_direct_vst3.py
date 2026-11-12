"""Pre-build safeguards; real compile/validator are separate native gates."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from skellforge.forge import ForgeError
from tools.check_skellnative_vst3 import inspect

ROOT = Path(__file__).resolve().parents[1] / "native" / "vst3"


class NativeVST3BlueprintTests(unittest.TestCase):
    def test_sdk_pinned_and_no_juce(self):
        cmake = (ROOT / "CMakeLists.txt").read_text("utf-8")
        self.assertIn("3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96", cmake)
        self.assertIn("GIT_SUBMODULES_RECURSE TRUE", cmake)
        self.assertIn("smtg_add_vst3plugin(SkellNativeGain", cmake)
        self.assertNotIn("juce", cmake.lower())

    def test_processor_controller_factory_complete(self):
        files = {p.name: p.read_text("utf-8") for p in (ROOT / "Source").glob("*")}
        self.assertEqual(len(files), 5)
        self.assertIn("kProcessorUID", files["NativeGainFactory.cpp"])
        self.assertIn("kControllerUID", files["NativeGainFactory.cpp"])
        self.assertIn("setState", files["NativeGainProcessor.cpp"])
        self.assertIn("getState", files["NativeGainProcessor.cpp"])
        self.assertIn("setComponentState", files["NativeGainController.cpp"])
        self.assertIn("kGainParam", files["NativeGainProcessor.cpp"])
        self.assertIn("kGainParam", files["NativeGainController.cpp"])
        self.assertIn("kernel_.process", files["NativeGainProcessor.cpp"])
        for source in files.values():
            self.assertNotIn("JuceHeader", source)
            self.assertNotIn("#include <juce", source)

    def test_unique_128_bit_uuids_in_source(self):
        ids = (ROOT / "Source" / "NativeGainIDs.h").read_text("utf-8")
        self.assertIn("DECLARE_UID(kProcessorUID", ids)
        self.assertIn("DECLARE_UID(kControllerUID", ids)
        self.assertEqual(ids.count("static DECLARE_UID("), 2)

    def test_binary_required_before_claiming_vst3(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with self.assertRaisesRegex(ForgeError, "Expected exactly one"):
                inspect(folder)
            bundle = folder / "SkellNativeGain.vst3"
            (bundle / "Contents" / "x86_64-win").mkdir(parents=True)
            binary = bundle / "Contents" / "x86_64-win" / "SkellNativeGain.vst3"
            binary.write_bytes(b"MZ" + b"\x00" * 200)
            with self.assertRaises(ForgeError):
                inspect(folder)


if __name__ == "__main__":
    unittest.main()
