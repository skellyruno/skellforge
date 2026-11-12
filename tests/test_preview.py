"""Preview checks: no native build needed to test integrity and traversal guards."""
from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from skellforge.forge import ForgeError
from skellforge.preview import SCENES, PNG_SIGNATURE, verify_preview_outputs


class PreviewValidationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.manifest = {"count": len(SCENES), "scenes": []}
        for name, (w,h) in SCENES.items():
            file = self.root / (name + ".png")
            # Synthetic header fixture (not a decoded image); only tests the
            # PNG signature/size checking code, not image quality.
            file.write_bytes(PNG_SIGNATURE + b"\x00\x00\x00\x0dIHDR"
                             + struct.pack(">II", w, h) + b"\x00" * 1200)
            self.manifest["scenes"].append({"file": name + ".png", "width": w, "height": h})
        self.write_manifest()

    def write_manifest(self):
        (self.root / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_valid_three_scene_report(self):
        report = verify_preview_outputs(self.root)
        self.assertEqual(set(report["scenes"]), set(SCENES))
        self.assertEqual(report["type"], "real-juce-editor")
        self.assertEqual(report["sizes"]["default"], [440, 310])

    def test_missing_screenshot_is_not_a_valid_preview(self):
        (self.root / "compact.png").unlink()
        with self.assertRaisesRegex(ForgeError, "Missing"):
            verify_preview_outputs(self.root)

    def test_wrong_png_dimensions_rejected(self):
        p = self.root / "default.png"
        b = bytearray(p.read_bytes())
        b[16:24] = struct.pack(">II", 222, 333)
        p.write_bytes(b)
        with self.assertRaisesRegex(ForgeError, "size mismatch"):
            verify_preview_outputs(self.root)

    def test_corrupt_image_signature_rejected(self):
        (self.root / "default.png").write_bytes(b"not a PNG" + b"x"*1200)
        with self.assertRaisesRegex(ForgeError, "Corrupt"):
            verify_preview_outputs(self.root)

    def test_no_path_traversal(self):
        self.manifest["scenes"][0]["file"] = "../default.png"
        self.write_manifest()
        with self.assertRaises(ForgeError):
            verify_preview_outputs(self.root)

    def test_cannot_claim_two_same_scene_captures(self):
        self.manifest["scenes"][0]["file"] = "default.png"
        self.write_manifest()
        with self.assertRaisesRegex(ForgeError, "Duplicate"):
            verify_preview_outputs(self.root)

    def test_incomplete_capture_count_rejected(self):
        self.manifest["count"] = 2
        self.write_manifest()
        with self.assertRaisesRegex(ForgeError, "incomplete"):
            verify_preview_outputs(self.root)

    def test_mismatched_scene_dimensions_rejected(self):
        self.manifest["scenes"][0]["width"] = 4
        self.write_manifest()
        with self.assertRaisesRegex(ForgeError, "metadata dimensions"):
            verify_preview_outputs(self.root)


if __name__ == "__main__":
    unittest.main()
