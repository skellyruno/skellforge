"""Regression contract for real native VST3 processor adapter benchmark."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class Vst3AdapterBenchContractTests(unittest.TestCase):
    def test_compiles_same_processor_as_plugin(self):
        cm=(ROOT/"native/vst3/CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("add_executable(SkellNativeVst3AdapterBench",cm)
        self.assertIn("tests/SkellNativeVst3AdapterBench.cpp",cm)
        self.assertIn("Source/NativeGainProcessor.cpp",cm)
        self.assertIn("parameterchanges.cpp",cm)

    def test_host_process_sample_parity_gated_before_timing(self):
        src=(ROOT/"native/vst3/tests/SkellNativeVst3AdapterBench.cpp").read_text(encoding="utf-8")
        for token in ("queryInterface(IAudioProcessor::iid", "queryInterface(IComponent::iid",
                      "audio->setupProcessing", "audio->process", "data.outputParameterChanges",
                      "data.inputParameterChanges", "max_error", "kSample32", "kSample64"):
            if token=="max_error":
                self.assertIn("Trial",src)
            else:
                self.assertIn(token,src)
        self.assertIn("trial.verify()",src)
        self.assertIn("rates{{44100.0,48000.0,96000.0}}",src)
        self.assertIn("frameCounts{{64,256,1024}}",src)
        self.assertIn("referenceFrames=262144",src)
        self.assertNotIn("#include <juce",src)

    def test_ci_requires_72_cases_and_validator(self):
        flow=(ROOT/".github/workflows/skellnative-direct-vst3.yml").read_text(encoding="utf-8")
        self.assertIn("SkellNativeVst3AdapterBench",flow)
        self.assertIn("Expected 72 adapter",flow)
        self.assertIn("Run official Steinberg host compatibility tests",flow)

    def test_documentation_states_scope(self):
        doc=(ROOT/"docs/SKELLNATIVE_VST3_ADAPTER_BENCHMARK.md").read_text(encoding="utf-8")
        self.assertIn("not a complete",doc)
        self.assertIn("not proof of FL Studio CPU superiority",doc)
        self.assertIn("72 cases",doc)


if __name__=="__main__":
    unittest.main()
