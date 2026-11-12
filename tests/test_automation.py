"""Regression tests for SkellForge automation, stable IDs, and JUCE UI codegen."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from skellforge.automation import (
    ParameterError, active_specs, registry_specs, sync_registry, unified_specs,
)
from skellforge.forge import create_project
from skellforge.local import verify_dsp_test_registered
from skellforge.studio import (
    StudioError, load_studio, regenerate, save_studio, validate_studio,
)


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name) / "fx-test"
        create_project("Skell Automation", self.project, "Sf96")

    @staticmethod
    def _drive():
        return {"id": "saturate_1", "type": "saturate", "enabled": False, "drive": 2.0}

    @staticmethod
    def _filter():
        return {"id": "lowpass_1", "type": "lowpass", "enabled": True, "cutoff_hz": 8000.0}

    def test_native_dsp_test_gate_never_accepts_zero_tests(self):
        build = self.project / "build"
        build.mkdir()
        with self.assertRaisesRegex(Exception, "compiled"):
            verify_dsp_test_registered(build)
        app = build / "Release" / "SkellForgeDspSmoke.exe"
        app.parent.mkdir()
        app.write_bytes(b"stub for registration test")
        with self.assertRaisesRegex(Exception, "registered"):
            verify_dsp_test_registered(build)
        (build / "CTestTestfile.cmake").write_text(
            'add_test(SkellForgeDspSmoke "Release/SkellForgeDspSmoke.exe")',
            encoding="utf-8")
        self.assertEqual(verify_dsp_test_registered(build), app)

    def test_generated_default_has_no_surprise_effects(self):
        doc = load_studio(self.project)
        self.assertEqual(active_specs(doc), [])
        params = (self.project / "Source" / "ForgeParameters.h").read_text()
        self.assertNotIn('ParameterID{"fx_', params)
        graph = (self.project / "Source" / "ForgeGraph.h").read_text()
        self.assertNotIn("std::tanh(sample", graph)
        self.assertIn("void bind(juce::AudioProcessorValueTreeState&", graph)
        self.assertIn("graph_.bind(parameters)", (self.project/"Source"/"PluginProcessor.cpp").read_text())

    def test_fx_ids_and_knob_bindings(self):
        doc = load_studio(self.project)
        doc["chain"].extend([self._drive(), self._filter()])
        doc["components"].append({
            "id": "effect_knob_1", "type": "effect_knob",
            "parameter_id": "fx_saturate_1_drive",
            "text": "DRIVE", "x": 265, "y": 145, "w": 100, "h": 108,
        })
        save_studio(self.project, doc)
        changed = regenerate(self.project)
        self.assertEqual(set(changed), {"ForgeGraph.h", "ForgeUI.h", "ForgeParameters.h"})
        ui = (self.project / "Source" / "ForgeUI.h").read_text()
        self.assertIn('state, "fx_saturate_1_drive", *knob', ui)
        self.assertIn("configureStudioKnob(*knob, 2", ui)
        self.assertIn("std::vector<std::unique_ptr<juce::Slider>>", ui)
        params = (self.project / "Source" / "ForgeParameters.h").read_text()
        self.assertIn('ParameterID{"fx_saturate_1_drive", 1}', params)
        self.assertIn('ParameterID{"fx_lowpass_1_cutoff_hz", 1}', params)
        graph = (self.project / "Source" / "ForgeGraph.h").read_text()
        self.assertNotIn("std::tanh(sample", graph)  # saturation bypassed
        self.assertIn('getRawParameterValue("fx_lowpass_1_cutoff_hz")', graph)
        self.assertEqual(regenerate(self.project), [])
        self.assertEqual([e["id"] for e in registry_specs(load_studio(self.project))],
                         ["fx_saturate_1_drive", "fx_lowpass_1_cutoff_hz"])

    def test_reorder_keeps_identical_apvts_catalog(self):
        doc = load_studio(self.project)
        doc["chain"].extend([self._drive(), self._filter()])
        save_studio(self.project, doc)
        regenerate(self.project)
        before = (self.project / "Source"/"ForgeParameters.h").read_bytes()
        doc["chain"][1], doc["chain"][2] = doc["chain"][2], doc["chain"][1]
        save_studio(self.project, doc)
        regenerate(self.project)
        self.assertEqual(before, (self.project/"Source"/"ForgeParameters.h").read_bytes())
        self.assertEqual(regenerate(self.project), [])

    def test_remove_retains_automation_as_retired_parameter(self):
        doc = load_studio(self.project)
        doc["chain"].append(self._drive())
        save_studio(self.project, doc)
        regenerate(self.project)
        doc["chain"].pop()
        save_studio(self.project, doc)
        regenerate(self.project)
        self.assertIn('ParameterID{"fx_saturate_1_drive", 1}',
                      (self.project/"Source"/"ForgeParameters.h").read_text())
        self.assertNotIn("std::tanh(sample",
                         (self.project/"Source"/"ForgeGraph.h").read_text())
        self.assertEqual([s["id"] for s in registry_specs(load_studio(self.project))],
                         ["fx_saturate_1_drive"])
        # A removed node cannot silently inherit the same previously-used ID.
        doc["chain"].append(self._drive())
        with self.assertRaisesRegex(ParameterError, "retired"):
            sync_registry(doc, load_studio(self.project))

    def test_saved_default_cannot_change_without_migration(self):
        doc = load_studio(self.project)
        doc["chain"].append(self._drive())
        save_studio(self.project, doc)
        doc["chain"][1]["drive"] = 8.0
        with self.assertRaisesRegex(StudioError, "locked"):
            save_studio(self.project, doc)
        self.assertEqual(load_studio(self.project)["chain"][1]["drive"], 2.0)

    def test_invalid_parameter_mapping_is_rejected(self):
        doc = load_studio(self.project)
        doc["components"].append({
            "id": "effect_knob_1", "type": "effect_knob",
            "parameter_id": "fx_fake_drive",
            "text": "FAKE", "x": 260, "y": 150, "w": 100, "h": 100,
        })
        with self.assertRaisesRegex(StudioError, "live DSP"):
            validate_studio(doc)
        doc["chain"].append(self._drive())
        doc["components"][-1]["parameter_id"] = "fx_saturate_1_drive"
        validate_studio(doc)
        duplicate = copy.deepcopy(doc["components"][-1])
        duplicate["id"] = "effect_knob_2"
        doc["components"].append(duplicate)
        with self.assertRaisesRegex(StudioError, "one visual knob"):
            validate_studio(doc)

    def test_unknown_or_forged_registry_is_rejected(self):
        doc = load_studio(self.project)
        doc["chain"].append(self._drive())
        save_studio(self.project, doc)
        doc["parameter_registry"][0]["minimum"] = -99.0
        with self.assertRaisesRegex(StudioError, "range"):
            validate_studio(doc)
        doc = load_studio(self.project)
        doc["parameter_registry"][0]["id"] = "fx_skell_fake"
        with self.assertRaises(StudioError):
            validate_studio(doc)

    def test_generated_header_preflight_is_all_or_nothing(self):
        doc = load_studio(self.project)
        before_ui = (self.project / "Source" / "ForgeUI.h").read_bytes()
        doc["components"].append({
            "id": "release_note", "type": "text",
            "text": "CHECK", "x": 24, "y": 262, "w": 120, "h": 22,
        })
        save_studio(self.project, doc)
        protected = self.project / "Source" / "ForgeParameters.h"
        protected.write_text("User authored safe header", encoding="utf-8")
        with self.assertRaisesRegex(StudioError, "Refusing"):
            regenerate(self.project)
        self.assertEqual(before_ui, (self.project / "Source" / "ForgeUI.h").read_bytes())

    def test_effect_knob_caption_and_mappings_are_bounded(self):
        doc = load_studio(self.project)
        doc["chain"].append(self._drive())
        doc["components"].append({
            "id": "fxcontrol", "type": "effect_knob",
            "parameter_id": "fx_saturate_1_drive",
            "text": "", "x": 265, "y": 148, "w": 110, "h": 108,
        })
        with self.assertRaisesRegex(StudioError, "captions"):
            validate_studio(doc)
        doc["components"][-1]["text"] = "DRIVE"
        validate_studio(doc)

    def test_output_stable_and_user_source_never_overwritten(self):
        doc = load_studio(self.project)
        original = (self.project / "Source"/"PluginProcessor.cpp").read_bytes()
        doc["chain"].append(self._drive())
        doc["chain"][1]["enabled"] = True
        save_studio(self.project, doc)
        regenerate(self.project)
        self.assertEqual(original, (self.project/"Source"/"PluginProcessor.cpp").read_bytes())
        self.assertIn("std::memory_order_relaxed", (self.project/"Source"/"ForgeGraph.h").read_text())
        header = self.project / "Source" / "ForgeParameters.h"
        header.write_text("custom user code", encoding="utf-8")
        with self.assertRaisesRegex(StudioError, "Refusing"):
            regenerate(self.project)


if __name__ == "__main__":
    unittest.main()
