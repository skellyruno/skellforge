"""Preview checks: no native build needed to test integrity and traversal guards."""
from __future__ import annotations

import json
import struct
import zlib
import tempfile
import unittest
from pathlib import Path

from skellforge.forge import ForgeError
from skellforge.preview import SCENES, PNG_SIGNATURE, verify_preview_outputs


class PreviewValidationTests(unittest.TestCase):
    @staticmethod
    def _chunk(kind: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(kind + payload) & 0xffffffff
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)

    @classmethod
    def _png(cls, width: int, height: int, *, first_filter: int = 0) -> bytes:
        """Genuine compact PNG fixture, not a fake signature-only header."""
        ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
        row = bytes((i * 73) & 255 for i in range(width * 4))
        raw = bytes([first_filter]) + row + (b"\0" + row) * (height - 1)
        return (PNG_SIGNATURE + cls._chunk(b"IHDR", ihdr)
                + cls._chunk(b"IDAT", zlib.compress(raw))
                + cls._chunk(b"IEND", b""))

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.manifest = {"count": len(SCENES), "scenes": []}
        for name, (w,h) in SCENES.items():
            file = self.root / (name + ".png")
            file.write_bytes(self._png(w, h))
            self.manifest["scenes"].append({"file": name + ".png", "width": w, "height": h})
        self.write_manifest()

    def write_manifest(self):
        (self.root / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_valid_three_scene_report(self):
        report = verify_preview_outputs(self.root)
        self.assertEqual(set(report["scenes"]), set(SCENES))
        self.assertEqual(report["type"], "real-juce-editor")
        self.assertEqual(report["sizes"]["default"], [440, 310])


    def test_crc_corruption_is_rejected(self):
        p = self.root / "compact.png"
        b = bytearray(p.read_bytes())
        b[-16] ^= 1  # damage IDAT CRC, preserve valid dimensions and header
        p.write_bytes(b)
        with self.assertRaisesRegex(ForgeError, "CRC mismatch"):
            verify_preview_outputs(self.root)

    def test_truncated_png_without_iend_is_rejected(self):
        p = self.root / "compact.png"
        p.write_bytes(p.read_bytes()[:-12])
        with self.assertRaisesRegex(ForgeError, "missing IEND"):
            verify_preview_outputs(self.root)

    def test_invalid_decoded_scanline_filter_is_rejected(self):
        (self.root / "compact.png").write_bytes(self._png(390, 260, first_filter=7))
        with self.assertRaisesRegex(ForgeError, "scanline filter"):
            verify_preview_outputs(self.root)

    def test_trailing_data_after_iend_is_rejected(self):
        p = self.root / "compact.png"
        p.write_bytes(p.read_bytes() + b"unexpected bytes")
        with self.assertRaisesRegex(ForgeError, "invalid IEND"):
            verify_preview_outputs(self.root)

    def test_missing_screenshot_is_not_a_valid_preview(self):
        (self.root / "compact.png").unlink()
        with self.assertRaisesRegex(ForgeError, "Missing"):
            verify_preview_outputs(self.root)

    def test_wrong_png_dimensions_rejected(self):
        p = self.root / "default.png"
        b = bytearray(p.read_bytes())
        b[16:24] = struct.pack(">II", 222, 333)
        # Keep the IHDR checksum valid so dimensions are tested independently.
        b[29:33] = struct.pack(">I", zlib.crc32(b[12:29]) & 0xffffffff)
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
