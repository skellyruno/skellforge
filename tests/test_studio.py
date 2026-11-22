import copy
import json
import struct
import tempfile
import unittest
from pathlib import Path

from skellforge.forge import create_project
from skellforge.studio import (
    StudioError, default_studio, init_studio, load_studio, regenerate,
    render_ui, render_graph, save_studio, validate_studio,
)
from skellforge.local import check_pe_x64, read_history, install_verified_vst3
from unittest.mock import patch


class StudioModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name) / "skell-pulse"

    def make(self):
        create_project("Skell Pulse", self.project, "SF94")
        return load_studio(self.project)

    def test_default_scene_generated_and_reserializable(self):
        data = self.make()
        self.assertEqual(data["schema"], "skellforge/studio/1")
        self.assertEqual(len(data["components"]), 4)
        self.assertEqual(data["chain"], [{"id": "gain", "type": "gain", "enabled": True}])
        self.assertTrue((self.project / "Source" / "ForgeUI.h").exists())
        self.assertTrue((self.project / "Source" / "ForgeGraph.h").exists())
        self.assertEqual(regenerate(self.project), [])

    def test_visual_label_changes_generated_cpp_not_user_cpp(self):
        doc = self.make()
        plugin_source = (self.project / "Source" / "PluginProcessor.cpp").read_bytes()
        doc["components"].append({
            "id": "my_note", "type": "text", "text": 'Hello "Skelly"',
            "x": 40, "y": 266, "w": 200, "h": 22,
        })
        save_studio(self.project, doc)
        self.assertEqual(regenerate(self.project), ["ForgeUI.h"])
        out = (self.project / "Source" / "ForgeUI.h").read_text()
        self.assertIn(r'Hello \"Skelly\"', out)
        self.assertEqual(plugin_source, (self.project / "Source" / "PluginProcessor.cpp").read_bytes())
        self.assertEqual(load_studio(self.project), doc)

    def test_graph_codegen_disabled_effect_maintains_unity_path(self):
        doc = self.make()
        doc["chain"].extend([
            {"id": "saturate_1", "type": "saturate", "enabled": False, "drive": 2.0},
            {"id": "lowpass_1", "type": "lowpass", "enabled": False, "cutoff_hz": 8000.0},
        ])
        save_studio(self.project, doc)
        regenerate(self.project)
        result = (self.project / "Source" / "ForgeGraph.h").read_text()
        self.assertNotIn("std::tanh(", result)
        self.assertNotIn("state_", result)

    def test_graph_enabled_nodes_emit_valid_literals_and_safe_processing(self):
        doc = self.make()
        doc["chain"].extend([
            {"id": "saturate_1", "type": "saturate", "enabled": True, "drive": 2.0},
            {"id": "lowpass_1", "type": "lowpass", "enabled": True, "cutoff_hz": 8000.0},
        ])
        save_studio(self.project, doc)
        regenerate(self.project)
        result = (self.project / "Source" / "ForgeGraph.h").read_text()
        self.assertIn("drive_0 = 2.0f;", result)
        self.assertIn("std::min(8000.0, rate * 0.45)", result)
        self.assertIn("std::isfinite(s[i])", result)
        self.assertIn("state_1_", result)
        self.assertEqual(regenerate(self.project), [])

    def test_rejects_out_of_bounds_and_duplicate_components(self):
        doc = default_studio()
        doc["components"][0]["x"] = 420
        with self.assertRaisesRegex(StudioError, "outside"):
            validate_studio(doc)
        doc = default_studio()
        doc["components"].append(copy.deepcopy(doc["components"][0]))
        with self.assertRaisesRegex(StudioError, "Duplicate"):
            validate_studio(doc)

    def test_rejects_reordered_gain_and_invalid_numeric_controls(self):
        doc = default_studio()
        doc["chain"].insert(0, {"id": "lowpass_1", "type": "lowpass", "enabled": True, "cutoff_hz": 1200})
        with self.assertRaisesRegex(StudioError, "first"):
            validate_studio(doc)
        doc = default_studio()
        doc["chain"].append({"id": "saturate_1", "type": "saturate", "enabled": True, "drive": float("nan")})
        with self.assertRaises(StudioError):
            validate_studio(doc)

    def test_readonly_guard_protects_modified_generated_file(self):
        self.make()
        header = self.project / "Source" / "ForgeUI.h"
        header.write_text("MANUALLY EDITED HEADER")
        with self.assertRaisesRegex(StudioError, "Refusing"):
            regenerate(self.project)

    def test_init_disallows_overwriting_existing_studio(self):
        self.make()
        with self.assertRaisesRegex(StudioError, "already initialized"):
            init_studio(self.project)


class NativeVST3VerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _fake_pe(self, path, machine=0x8664, magic=0x20B):
        payload = bytearray(256)
        payload[:2] = b"MZ"
        struct.pack_into("<I", payload, 0x3C, 128)
        payload[128:132] = b"PE\x00\x00"
        struct.pack_into("<H", payload, 132, machine)
        struct.pack_into("<H", payload, 152, magic)
        path.write_bytes(payload)

    def test_accepts_pe32plus_x64_header(self):
        path = self.root / "Plugin.vst3"
        self._fake_pe(path)
        check_pe_x64(path)

    def test_rejects_false_or_wrong_arch_binary(self):
        path = self.root / "Plugin.vst3"
        path.write_bytes(b"pretend plugin")
        with self.assertRaisesRegex(Exception, "Not a Windows PE"):
            check_pe_x64(path)
        self._fake_pe(path, machine=0x14C)
        with self.assertRaisesRegex(Exception, "Not an x64"):
            check_pe_x64(path)

    def test_empty_build_history(self):
        self.assertEqual(read_history(self.root), [])

    def test_opt_in_install_with_backup_and_rollback_copy(self):
        project = self.root / "project"
        create_project("Skell Pulse", project, "SF94")
        bundle = project / "build" / "SkellPulse_artefacts" / "Release" / "VST3" / "Skell Pulse.vst3"
        built = bundle / "Contents" / "x86_64-win" / "Skell Pulse.vst3"
        built.parent.mkdir(parents=True)
        self._fake_pe(built)
        folder = self.root / "my-vst3"
        folder.mkdir()
        previous = folder / bundle.name
        previous.mkdir()
        (previous / "old.txt").write_text("previous version")
        with patch("skellforge.local.sys.platform", "win32"):
            result = install_verified_vst3(project, folder)
        self.assertTrue(Path(result["installed"]).samefile(previous))
        self.assertTrue((previous / "Contents" / "x86_64-win" / "Skell Pulse.vst3").is_file())
        self.assertFalse((previous / "old.txt").exists())
        backup = Path(result["backup"])
        self.assertEqual((backup / "old.txt").read_text(), "previous version")
        self.assertFalse(any(folder.glob(".skellforge-stage-*")))
        self.assertFalse(any(folder.glob(".skellforge-old-*")))

    def test_invalid_bundle_cannot_touch_existing_install(self):
        project = self.root / "project"
        create_project("Skell Pulse", project, "SF94")
        bundle = project / "build" / "SkellPulse_artefacts" / "Release" / "VST3" / "Skell Pulse.vst3"
        built = bundle / "Contents" / "x86_64-win" / "Skell Pulse.vst3"
        built.parent.mkdir(parents=True)
        built.write_bytes(b"not a real binary")
        folder = self.root / "scan"
        folder.mkdir()
        current = folder / "Skell Pulse.vst3"
        current.mkdir()
        (current / "old.txt").write_text("safe")
        with patch("skellforge.local.sys.platform", "win32"):
            with self.assertRaisesRegex(Exception, "Not a Windows PE"):
                install_verified_vst3(project, folder)
        self.assertEqual((current / "old.txt").read_text(), "safe")


if __name__ == "__main__":
    unittest.main()
