import json
import runpy
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from skellforge.audit import audit_project

from skellforge.forge import (
    CORE_REV, ForgeError, create_project, identity, package_project,
    validate_project, build_project, main,
)


class ForgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "skell-pulse"

    def make(self, code="Sf01"):
        return create_project("Skell Pulse", self.project, code)

    def test_generated_project_is_valid_and_vst3_only(self):
        self.make()
        data = validate_project(self.project)
        self.assertEqual(data["target"], "SkellPulse")
        self.assertEqual(data["plugin_code"], "Sf01")
        self.assertEqual(data["formats"], ["VST3"])
        cmake = (self.project / "CMakeLists.txt").read_text()
        self.assertIn("FORMATS VST3", cmake)
        self.assertNotIn("Standalone", cmake)
        self.assertIn(CORE_REV, cmake)
        self.assertNotIn("@@", cmake)
        self.assertIn("find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)", cmake)
        self.assertIn("tools/normalize_moduleinfo.py", cmake)
        self.assertIn("add_custom_command(TARGET SkellPulse_VST3 POST_BUILD", cmake)
        self.assertTrue((self.project / "tools" / "normalize_moduleinfo.py").is_file())
        proc = (self.project / "Source" / "PluginProcessor.cpp").read_text()
        self.assertIn("gain_db", proc)
        self.assertIn("0.0f", proc)
        self.assertIn("gain_.skip(frames)", proc)

    def test_juce_moduleinfo_is_normalized_and_duplicate_keys_fail_closed(self):
        self.make()
        normalize = runpy.run_path(
            str(self.project / "tools" / "normalize_moduleinfo.py")
        )["normalize"]
        bundle = (self.project / "build" / "SkellPulse_artefacts" / "Release"
                  / "VST3" / "Skell Pulse.vst3")
        metadata = bundle / "Contents" / "Resources" / "moduleinfo.json"
        metadata.parent.mkdir(parents=True)
        source = """{
  "Name": "Skell Pulse",
  "Version": "0.1.0",
  "Description": "literal ,} and ,] stay inside this string",
  "Factory Info": {
    "Vendor": "Skell Audio",
    "Flags": {"Unicode": true,},
  },
  "Classes": [
    {"CID": "ABCDEF019182FAEB536B417553463930",
     "Category": "Audio Module Class", "Name": "Skell Pulse",
     "Vendor": "Skell Audio",},
    {"CID": "ABCDEF011234ABCD536B417553463930",
     "Category": "Component Controller Class", "Name": "Skell Pulse",
     "Vendor": "Skell Audio",},
  ],
}"""
        metadata.write_text(source, encoding="utf-8")
        normalize(self.project / "build", "Skell Pulse")
        normalized = metadata.read_text(encoding="utf-8")
        data = json.loads(normalized)
        self.assertEqual(data["Description"], "literal ,} and ,] stay inside this string")
        self.assertEqual(len(data["Classes"]), 2)
        self.assertTrue(normalized.endswith("\n"))
        self.assertEqual(normalize(self.project / "build", "Skell Pulse").resolve(), metadata.resolve())

        duplicate = source.replace(
            '"Name": "Skell Pulse",',
            '"Name": "Skell Pulse",\n  "Name": "Ambiguous",',
            1,
        )
        metadata.write_text(duplicate, encoding="utf-8")
        original = metadata.read_bytes()
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            normalize(self.project / "build", "Skell Pulse")
        self.assertEqual(metadata.read_bytes(), original)

        invalid_category = source.replace(
            '"Category": "Audio Module Class"',
            '"Category": []',
            1,
        )
        metadata.write_text(invalid_category, encoding="utf-8")
        original = metadata.read_bytes()
        with self.assertRaisesRegex(ValueError, "supported string Category"):
            normalize(self.project / "build", "Skell Pulse")
        self.assertEqual(metadata.read_bytes(), original)

    def test_output_is_not_overwritten(self):
        self.make()
        original = (self.project / "skellforge.json").read_bytes()
        with self.assertRaisesRegex(ForgeError, "overwrite"):
            self.make()
        self.assertEqual(original, (self.project / "skellforge.json").read_bytes())

    def test_codes_are_case_insensitively_reserved(self):
        with self.assertRaisesRegex(ForgeError, "already used"):
            self.make("sk01")
        self.assertFalse(self.project.exists())

    def test_identity_rejects_malformed_inputs(self):
        for name in ("", "1Plugin", 'Skell "Escape"', "X", "../oops"):
            with self.subTest(name=name):
                with self.assertRaises(ForgeError):
                    identity(name, "Sf01")
        for code in ("SK1", "12345", "A$11", "SK_1"):
            with self.subTest(code=code):
                with self.assertRaises(ForgeError):
                    identity("Skell Pulse", code)
        with self.assertRaises(ForgeError):
            identity("Skell Pulse", "Sf01", core_rev="main")

    def test_manifest_tampering_detected(self):
        self.make()
        path = self.project / "skellforge.json"
        manifest = json.loads(path.read_text())
        manifest["plugin_code"] = "BBBB"
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ForgeError, "CMake identity"):
            validate_project(self.project)

    def test_world_manifest_identity_detected(self):
        self.make()
        path = self.project / "skellworld.json"
        manifest = json.loads(path.read_text())
        manifest["bundle_id"] = "audio.skell.wrong"
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ForgeError, "SkellWorld"):
            validate_project(self.project)

    def test_missing_source_detected(self):
        self.make()
        (self.project / "Source" / "PluginEditor.cpp").unlink()
        with self.assertRaisesRegex(ForgeError, "Required project file"):
            validate_project(self.project)

    def test_package_fails_without_real_bundle(self):
        self.make()
        with self.assertRaisesRegex(ForgeError, "No build"):
            package_project(self.project)

    def test_package_exact_bundle_and_verify_zip(self):
        self.make()
        bundle = self.project / "build" / "SkellPulse_artefacts" / "Release" / "VST3" / "Skell Pulse.vst3"
        binary = bundle / "Contents" / "x86_64-win" / "Skell Pulse.vst3"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"example VST3 signature surrogate - not a distributable binary")
        metadata = bundle / "Contents" / "Resources" / "moduleinfo.json"
        metadata.parent.mkdir(parents=True)
        metadata.write_text(json.dumps({
            "Name": "Skell Pulse",
            "Version": "0.1.0",
            "Factory Info": {"Vendor": "Skell Audio"},
            "Classes": [
                {"CID": "ABCDEF019182FAEB536B417553463930",
                 "Category": "Audio Module Class", "Name": "Skell Pulse", "Vendor": "Skell Audio"},
                {"CID": "ABCDEF011234ABCD536B417553463930",
                 "Category": "Component Controller Class", "Name": "Skell Pulse", "Vendor": "Skell Audio"},
            ],
        }, indent=2) + "\n", encoding="utf-8")
        output = package_project(self.project)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.namelist(), [
                "Skell Pulse.vst3/Contents/Resources/moduleinfo.json",
                "Skell Pulse.vst3/Contents/x86_64-win/Skell Pulse.vst3",
            ])
        with self.assertRaisesRegex(ForgeError, "overwrite"):
            package_project(self.project)

    def test_package_detects_duplicates(self):
        self.make()
        root = self.project / "build" / "SkellPulse_artefacts"
        for name in ("one.vst3", "two.vst3"):
            path = root / "Release" / "VST3" / name
            path.mkdir(parents=True)
            (path / "plugin.vst3").write_bytes(b"mock")
        with self.assertRaisesRegex(ForgeError, "exactly one"):
            package_project(self.project)

    def test_non_windows_build_is_explicit(self):
        self.make()
        with patch("skellforge.forge.sys.platform", "linux"):
            with self.assertRaisesRegex(ForgeError, "requires Windows"):
                build_project(self.project)

    def test_read_only_audit_of_generated_plugin(self):
        self.make()
        before = (self.project / "CMakeLists.txt").read_bytes()
        report = audit_project(self.project)
        self.assertTrue(report["juce_target_detected"])
        self.assertTrue(report["skellcore_dsp_link_detected"])
        self.assertEqual(report["plugin_code"], "Sf01")
        self.assertEqual(report["formats_detected"], ["VST3"])
        self.assertIn("gain_db", report["parameter_ids_detected"])
        self.assertFalse(report["safe_to_automatically_migrate"])
        self.assertEqual(before, (self.project / "CMakeLists.txt").read_bytes())

    def test_audit_missing_cmake_reports_warning(self):
        path = self.root / "old-plugin"
        path.mkdir()
        report = audit_project(path)
        self.assertFalse(report["root_cmake_found"])
        self.assertTrue(report["warnings"])

    def test_cli_roundtrip(self):
        self.assertEqual(main(["new", "Skell Pulse", str(self.project), "--code", "Sf01"]), 0)
        self.assertEqual(main(["validate", str(self.project)]), 0)
        result = subprocess.run([sys.executable, "-m", "skellforge", "--help"],
                                capture_output=True, text=True, check=True)
        self.assertIn("package", result.stdout)


if __name__ == "__main__":
    unittest.main()
