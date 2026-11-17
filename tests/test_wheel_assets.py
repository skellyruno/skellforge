"""The vendored wheel assets must stay identical to the current source templates.

During the compatibility period the originals stay at the repository root.
"""
import unittest
from pathlib import Path
from skellforge import forge


class WheelAssetsTests(unittest.TestCase):
    def test_templates_are_packaged_in_the_module(self):
        self.assertEqual(forge.TEMPLATES, Path(forge.__file__).resolve().parent / "data" / "templates")
        self.assertTrue(forge.KNOWN_CODES.is_file())
        for relative in ("CMakeLists.txt.in", ".gitignore.in",
                         ".github/workflows/build.yml.in",
                         "Source/PluginProcessor.cpp.in", "Source/PluginEditor.cpp.in",
                         "tools/normalize_moduleinfo.py.in"):
            with self.subTest(relative=relative):
                self.assertTrue((forge.TEMPLATES / relative).is_file())

    def test_source_resource_mirror_has_no_drift(self):
        root = Path(__file__).resolve().parents[1]
        for source in (root / "templates").rglob("*"):
            if source.is_file():
                other = forge.TEMPLATES / source.relative_to(root / "templates")
                with self.subTest(path=str(source.relative_to(root))):
                    self.assertEqual(source.read_bytes(), other.read_bytes())
        self.assertEqual((root / "config" / "known_codes.json").read_bytes(),
                         forge.KNOWN_CODES.read_bytes())


if __name__ == "__main__":
    unittest.main()
