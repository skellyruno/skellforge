import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

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
        proc = (self.project / "Source" / "PluginProcessor.cpp").read_text()
        self.assertIn("gain_db", proc)
        self.assertIn("0.0f", proc)
        self.assertIn("gain_.skip(frames)", proc)

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
        output = package_project(self.project)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.namelist(), ["Skell Pulse.vst3/Contents/x86_64-win/Skell Pulse.vst3"])
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

    def test_cli_roundtrip(self):
        self.assertEqual(main(["new", "Skell Pulse", str(self.project), "--code", "Sf01"]), 0)
        self.assertEqual(main(["validate", str(self.project)]), 0)
        result = subprocess.run([sys.executable, "-m", "skellforge", "--help"],
                                capture_output=True, text=True, check=True)
        self.assertIn("package", result.stdout)


if __name__ == "__main__":
    unittest.main()
