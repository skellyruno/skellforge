"""No-overwrite, identity and SkellLang native Gain scaffold regressions."""
from __future__ import annotations

import json
import runpy
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from skellforge.forge import ForgeError, main
from skellforge.native_scaffold import SOURCE, create_native_project


class NewNativeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sdk = self.root / "skellnative"
        source = self.sdk / "native/vst3/Source"
        source.mkdir(parents=True)
        for path in SOURCE:
            (source / path).write_text("// original SkellNative reference\n", encoding="utf-8")
        (source / "NativeGainIDs.h").write_text(
            "static DECLARE_UID(kProcessorUID, 0xD74FB65B, 0xC388486F, 0xA8ACC80F, 0x23B6DA4E);\n"
            "static DECLARE_UID(kControllerUID, 0x79BFB11F, 0xA5BD4C50, 0x9602ED4E, 0xC4E515D8);\n"
            'inline constexpr char kProductId[] = "skellnative.gain.prototype";\n', encoding="utf-8")
        (source / "NativeGainFactory.cpp").write_text(
            '"SkellNative Gain Prototype"\n"SkellNative Gain Controller"\n', encoding="utf-8")
        (source / "NativeGainController.cpp").write_text(
            '#include "SkellDrawWin32.h"\n'
            "using namespace Steinberg::Vst;\n"
            'parameters.addParameter(STR16("Gain"), nullptr, 0, 0.5,\n'
            '                                ParameterInfo::kCanAutomate, kGainParam);\n'
            'parameters.addParameter(STR16("Output Peak"), nullptr, 0, 0.0,\n'
            '                                ParameterInfo::kIsReadOnly, kOutputPeakParam);\n',
            encoding="utf-8")
        for required in ("native/include/SkellNative/Dsp.h",
                         "native/vst3/Source/ControlParameter.h",
                         "native/skelldraw/include/SkellDraw/Win32Painter.h"):
            path = self.sdk / required
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("// sdk\n", encoding="utf-8")

    def new(self, label="Skell Fixture", name="demo"):
        return create_native_project(label, self.root / name, "QZ92", self.sdk)

    def test_generates_distinct_ids_and_juceless_cmake(self):
        out = self.new()
        manifest = json.loads((out / "skellnative.json").read_text())
        self.assertEqual(manifest["status"], "experimental")
        self.assertEqual(manifest["parameter_ids"], [1000, 1001])
        self.assertEqual(len(manifest["processor_cid"]), 32)
        self.assertNotEqual(manifest["processor_cid"], manifest["controller_cid"])
        self.assertNotEqual(manifest["processor_cid"], "D74FB65BC388486FA8ACC80F23B6DA4E")
        source = (out / "Source/NativeGainIDs.h").read_text()
        self.assertIn(manifest["bundle_id"], source)
        self.assertNotIn("skellnative.gain.prototype", source)
        cmake = (out / "CMakeLists.txt").read_text()
        self.assertIn("SKELLNATIVE_ROOT", cmake)
        self.assertIn("SMTG_ENABLE_VSTGUI_SUPPORT OFF", cmake)
        self.assertIn("SteinbergValidator", cmake)
        self.assertNotIn("@@D@@", cmake)
        self.assertNotIn("JUCE", cmake)
        self.assertIn('parameter gain 1000 "Gain"', (out / "Gain.skell").read_text())
        controller = (out / "Source/NativeGainController.cpp").read_text()
        self.assertIn('#include "GainControls.inc"', controller)
        self.assertIn("new ControlParameter(controls[1])", controller)
        for file in SOURCE:
            self.assertTrue((out / "Source" / file).is_file(), file)

    def test_ids_deterministic_but_unique_for_other_product(self):
        first = json.loads((self.new(name="first") / "skellnative.json").read_text())
        again = json.loads((self.new(name="second") / "skellnative.json").read_text())
        different = json.loads((self.new(label="Skell Other", name="third") / "skellnative.json").read_text())
        self.assertEqual(first["processor_cid"], again["processor_cid"])
        self.assertNotEqual(first["processor_cid"], different["processor_cid"])
        self.assertNotEqual(first["state_product_key"], different["state_product_key"])

    def test_rejects_overwrite_and_preserves_existing_bytes(self):
        output = self.new()
        original = (output / "Source/NativeGainIDs.h").read_bytes()
        with self.assertRaises(ForgeError):
            self.new()
        self.assertEqual(original, (output / "Source/NativeGainIDs.h").read_bytes())

    def test_rejects_incomplete_sdk_and_unsafe_output(self):
        with self.assertRaises(ForgeError):
            create_native_project("Skell Fixture", self.sdk / "generated", "QZ92", self.sdk)
        (self.sdk / "native/vst3/Source/NativeGainFactory.cpp").unlink()
        with self.assertRaises(ForgeError):
            self.new()
        self.assertFalse((self.root / "demo").exists())

    def test_fails_closed_on_modified_reference_markers(self):
        file = self.sdk / "native/vst3/Source/NativeGainIDs.h"
        file.write_text("DECLARE_UID changed\n", encoding="utf-8")
        with self.assertRaises(ForgeError):
            self.new()
        self.assertFalse((self.root / "demo").exists())

    def test_cli_invocation(self):
        with redirect_stdout(StringIO()) as captured:
            result = main(["new-native", "Skell Fixture", str(self.root / "cli"),
                           "--code", "QZ92", "--sdk", str(self.sdk)])
        self.assertEqual(result, 0)
        self.assertIn("experimental JUCE-free", captured.getvalue())
        self.assertTrue((self.root / "cli/Gain.skell").exists())

    def test_generated_strict_moduleinfo(self):
        out = self.new()
        manifest = json.loads((out / "skellnative.json").read_text())
        normalize = runpy.run_path(str(out / "tools/normalize_moduleinfo.py"))["normalize"]
        bundle = self.root / "build/VST3/Release/Skell Fixture.vst3"
        path = bundle / "Contents/Resources/moduleinfo.json"
        path.parent.mkdir(parents=True)
        doc = {"Name": "Skell Fixture", "Version": "0.1.0",
               "Classes": [
                   {"CID": manifest["processor_cid"], "Category": "Audio Module Class"},
                   {"CID": manifest["controller_cid"], "Category": "Component Controller Class"},
               ]}
        path.write_text(json.dumps(doc)[:-1] + ",}", encoding="utf-8")
        normalize(self.root / "build", "Skell Fixture",
                  manifest["processor_cid"], manifest["controller_cid"])
        self.assertEqual(json.loads(path.read_text()), doc)
        doc["Classes"][0]["CID"] = "WRONG"
        path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(ValueError):
            normalize(self.root / "build", "Skell Fixture",
                      manifest["processor_cid"], manifest["controller_cid"])

    def test_moduleinfo_schema_errors_are_actionable_and_non_mutating(self):
        out = self.new()
        manifest = json.loads((out / "skellnative.json").read_text())
        normalize = runpy.run_path(str(out / "tools/normalize_moduleinfo.py"))["normalize"]
        bundle = self.root / "build/VST3/Release/Skell Fixture.vst3"
        path = bundle / "Contents/Resources/moduleinfo.json"
        path.parent.mkdir(parents=True)
        invalid_docs = [
            [],
            None,
            {"Name": "Skell Fixture", "Version": "0.1.0", "Classes": "not-an-array"},
            {"Name": "Skell Fixture", "Version": "0.1.0", "Classes": [None, {}]},
            {"Name": "Skell Fixture", "Version": "0.1.0",
             "Classes": [{"CID": [], "Category": "Audio Module Class"},
                         {"CID": "controller", "Category": "Component Controller Class"}]},
            {"Name": "Skell Fixture", "Version": "0.1.0",
             "Classes": [{"CID": "processor", "Category": []},
                         {"CID": "controller", "Category": "Component Controller Class"}]},
        ]
        for doc in invalid_docs:
            with self.subTest(document=doc):
                path.write_text(json.dumps(doc), encoding="utf-8")
                original = path.read_bytes()
                with self.assertRaisesRegex(ValueError, "moduleinfo.json root|factory class objects|string CID and Category"):
                    normalize(self.root / "build", "Skell Fixture",
                              manifest["processor_cid"], manifest["controller_cid"])
                self.assertEqual(path.read_bytes(), original)

    def test_duplicate_moduleinfo_keys_fail_closed_without_mutation(self):
        out = self.new()
        manifest = json.loads((out / "skellnative.json").read_text())
        normalize = runpy.run_path(str(out / "tools/normalize_moduleinfo.py"))["normalize"]
        bundle = self.root / "build/VST3/Release/Skell Fixture.vst3"
        path = bundle / "Contents/Resources/moduleinfo.json"
        path.parent.mkdir(parents=True)
        processor = manifest["processor_cid"]
        controller = manifest["controller_cid"]
        raw_documents = [
            '{"Name":"Skell Fixture","Name":"Other","Version":"0.1.0","Classes":[]}',
            ('{"Name":"Skell Fixture","Version":"0.1.0","Classes":['
             '{"CID":"' + processor + '","CID":"duplicate","Category":"Audio Module Class"},'
             '{"CID":"' + controller + '","Category":"Component Controller Class"}]}'),
            ('{"Name":"Skell Fixture","Version":"0.1.0","Classes":['
             '{"CID":"' + processor + '","Category":"Audio Module Class"},'
             '{"CID":"' + controller + '","Category":"Component Controller Class",'
             '"Category":"Audio Module Class"}],}'),
        ]
        for source in raw_documents:
            with self.subTest(source=source):
                path.write_text(source, encoding="utf-8")
                original = path.read_bytes()
                with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
                    normalize(self.root / "build", "Skell Fixture", processor, controller)
                self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
