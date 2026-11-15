"""Optional parameter metadata and experimental build switch regressions."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from skellforge import forge


class ParameterSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "plugin"
        forge.create_project("Skell Pulse", self.project, "Sf01")

    def test_generated_range_is_locked(self):
        path = self.project / "skellforge.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(value["parameters"]["gain_db"],
                         {"min": -24.0, "max": 24.0, "step": 1.0, "default": 0.0})
        source = self.project / "Source" / "PluginProcessor.cpp"
        original = source.read_text(encoding="utf-8")
        self.assertIn("(-24.0f, 24.0f, 1.0f), 0.0f", original)
        source.write_text(original.replace("(-24.0f, 24.0f, 1.0f), 0.0f",
                                           "(-24.0f, 24.0f, 0.5f), 0.0f"), encoding="utf-8")
        with self.assertRaisesRegex(forge.ForgeError, "Parameter 'gain_db' changed"):
            forge.validate_project(self.project)

    def test_legacy_manifest_without_metadata_is_valid(self):
        path = self.project / "skellforge.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        del value["parameters"]
        path.write_text(json.dumps(value), encoding="utf-8")
        forge.validate_project(self.project)

    def test_invalid_metadata_fails(self):
        path = self.project / "skellforge.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["parameters"]["gain_db"]["default"] = "0"
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(forge.ForgeError, "Invalid skellforge.json"):
            forge.validate_project(self.project)

    def test_static_runtime_opt_in_is_passed_to_cmake(self):
        with patch.object(forge.sys, "platform", "win32"), \
             patch.object(forge.shutil, "which", return_value="cmake"), \
             patch.object(forge.subprocess, "run") as run:
            forge.build_project(self.project, static_runtime=True)
            self.assertIn("-DSKELLFORGE_STATIC_RUNTIME=ON", run.call_args_list[0].args[0])


if __name__ == "__main__":
    unittest.main()
