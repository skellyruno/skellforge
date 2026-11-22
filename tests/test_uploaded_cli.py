"""CLI tests for the uploaded maintenance features."""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

def pe64_fixture(machine=0x8664, magic=0x20b):
    """Small PE32+ AMD64 structural fixture; not a runnable DLL."""
    image = bytearray(512)
    image[:2] = b"MZ"
    image[0x3c:0x40] = (0x80).to_bytes(4, "little")
    image[0x80:0x84] = b"PE\\x00\\x00"
    image[0x84:0x86] = machine.to_bytes(2, "little")
    image[0x94:0x96] = (0xf0).to_bytes(2, "little")
    image[0x98:0x9a] = magic.to_bytes(2, "little")
    return bytes(image)



from skellforge import forge


class UploadedCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "plugin"
        forge.create_project("Skell Pulse", self.project, "Sf01")

    def test_code_suggestions(self):
        codes = forge.suggest_codes("Skell Pulse")
        self.assertEqual(len(codes), 3)
        self.assertEqual(len({c.casefold() for c in codes}), 3)
        for code in codes:
            self.assertIsNone(forge.known_code_owner(code))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(forge.main(["codes", "check", "sk01"]), 1)
            self.assertEqual(forge.main(["codes", "check", "SZ90"]), 0)

    def test_validate_json_and_upgrade_core(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(forge.main(["validate", str(self.project), "--json"]), 0)
        self.assertEqual(json.loads(output.getvalue())["valid"], True)
        old = forge.CORE_REV
        new = "a" * 40
        old_world = (self.project / "skellworld.json").read_bytes()
        self.assertEqual(forge.upgrade_core(self.project, new), (old, new))
        self.assertEqual(forge.validate_project(self.project)["core_revision"], new)
        self.assertEqual((self.project / "skellworld.json").read_bytes(), old_world)
        with self.assertRaisesRegex(forge.ForgeError, "already pinned"):
            forge.upgrade_core(self.project, new)

    def test_vst3_sidecar(self):
        binary = self.project / "build" / "SkellPulse_artefacts" / "Release" / "VST3" / "Skell Pulse.vst3" / "Contents" / "x86_64-win" / "Skell Pulse.vst3"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(pe64_fixture())
        bundle = binary.parents[2]
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
        package = forge.package_project(self.project)
        sidecar = Path(str(package) + ".sha256")
        self.assertEqual(sidecar.read_text(encoding="ascii"), hashlib.sha256(package.read_bytes()).hexdigest() + "  " + package.name + "\n")
        with self.assertRaisesRegex(forge.ForgeError, "overwrite"):
            forge.package_project(self.project)


if __name__ == "__main__":
    unittest.main()
