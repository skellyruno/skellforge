"""Exercise real Windows junctions without requiring symlink privileges."""
import os
import subprocess
import unittest

from skellforge.audit import find_parameter_ranges, find_string_literals, scan_parameter_ids
from skellforge.forge import ForgeError, package_project
from test_hardening import ProjectCase


@unittest.skipUnless(os.name == "nt", "Windows junction regression")
class JunctionTests(ProjectCase):
    def junction(self, link, target):
        subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)],
                       check=True, capture_output=True)
        self.addCleanup(link.rmdir)

    def test_literal_scan_does_not_follow_cycle(self):
        self.make()
        self.junction(self.project / "Source" / "cycle", self.project)
        result = find_string_literals(self.project, ["missing"], limit=20)
        self.assertTrue(result["complete"])
        self.assertEqual(result["found"], set())

    def test_scans_skip_external_junction(self):
        self.make()
        external = self.root / "external"
        external.mkdir()
        (external / "private.cpp").write_text(
            'ParameterID{"private_id", 1}, "Private", '
            'NormalisableRange<float>(0, 1, 0), 0.5);')
        self.junction(self.project / "Source" / "external", external)
        self.assertNotIn("private_id", scan_parameter_ids(self.project)["parameter_ids"])
        self.assertEqual(find_parameter_ranges(self.project, ["private_id"]), {})
        self.assertEqual(find_string_literals(self.project, ["private_id"])["found"], set())

    def test_packaging_rejects_external_junction_before_export(self):
        self.make()
        self.fake_bundle("Release", "VST3")
        bundle = (self.project / "build/SkellPulse_artefacts/Release/VST3/Skell Pulse.vst3")
        external = self.root / "external"
        external.mkdir()
        (external / "private.txt").write_text("outside bundle")
        self.junction(bundle / "external", external)
        output = self.root / "unsafe.zip"
        with self.assertRaisesRegex(ForgeError, "reparse point"):
            package_project(self.project, output)
        self.assertFalse(output.exists())
        self.assertFalse(output.with_name(output.name + ".sha256").exists())

    def test_packaging_rejects_junction_at_build_root(self):
        self.make()
        self.fake_bundle("Release", "VST3")
        build = self.project / "build"
        external = self.root / "external-build"
        build.rename(external)
        self.junction(build, external)
        with self.assertRaisesRegex(ForgeError, "reparse point"):
            package_project(self.project)
