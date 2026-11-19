import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skellforge.forge import CORE_REV, _pinned_juce_revision, doctor, main


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make_juce(self, root):
        root.mkdir(parents=True, exist_ok=True)
        (root / "CMakeLists.txt").write_text("project(JUCE)\\n", encoding="utf-8")
        for module, header in (
            ("juce_core", "juce_core.h"),
            ("juce_audio_processors", "juce_audio_processors.h"),
        ):
            module_root = root / "modules" / module
            module_root.mkdir(parents=True)
            (module_root / header).write_text("#pragma once\\n", encoding="utf-8")

    def make_core(self, root, *, nested=False):
        source_root = root / "SkellCore" if nested else root
        include_root = source_root / "include" / "SkellCore"
        include_root.mkdir(parents=True)
        (source_root / "CMakeLists.txt").write_text(
            "add_library(SkellCore::DSP ALIAS SkellCoreDSP)\\n"
            "add_library(SkellCore::UI ALIAS SkellCoreUI)\\n",
            encoding="utf-8",
        )
        (include_root / "Core.h").write_text("#pragma once\\n", encoding="utf-8")
        return source_root

    def run_doctor(self, juce_path=None, core_path=None, *, cmake="/usr/bin/cmake", git="/usr/bin/git"):
        def which(binary):
            return {"cmake": cmake, "git": git}.get(binary)

        with patch("skellforge.forge.shutil.which", side_effect=which):
            with patch("builtins.print") as output:
                ready = doctor(juce_path, core_path)
        rendered = "\\n".join(
            " ".join(str(value) for value in call.args)
            for call in output.call_args_list
        )
        return ready, rendered

    def test_default_paths_report_pinned_fetch_content_dependencies(self):
        ready, output = self.run_doctor()
        self.assertTrue(ready)
        self.assertIn(
            f"JUCE: CMake FetchContent (pinned {_pinned_juce_revision()}; fetched during configure)",
            output,
        )
        self.assertIn(
            f"SkellCore: CMake FetchContent (pinned {CORE_REV}; fetched during configure)",
            output,
        )
        self.assertIn("network access is required on first configure", output)

    def test_valid_local_paths_do_not_require_git(self):
        juce = self.root / "JUCE"
        core = self.root / "skellcore-vst-template"
        self.make_juce(juce)
        self.make_core(core, nested=True)

        ready, output = self.run_doctor(juce, core, git=None)
        self.assertTrue(ready)
        self.assertIn("JUCE: local source", output)
        self.assertIn("SkellCore: local source", output)
        self.assertIn("Dependency fetch: not required", output)

    def test_cmake_only_local_roots_are_rejected(self):
        juce = self.root / "not-juce"
        core = self.root / "not-skellcore"
        juce.mkdir()
        core.mkdir()
        (juce / "CMakeLists.txt").write_text("project(Unrelated)\\n", encoding="utf-8")
        (core / "CMakeLists.txt").write_text("project(Unrelated)\\n", encoding="utf-8")

        ready, output = self.run_doctor(juce, core)
        self.assertFalse(ready)
        self.assertIn("JUCE: INVALID local path", output)
        self.assertIn("SkellCore: INVALID local path", output)

    def test_invalid_local_paths_are_reported_as_not_ready(self):
        juce = self.root / "missing-juce"
        core = self.root / "missing-core"
        ready, output = self.run_doctor(juce, core)
        self.assertFalse(ready)
        self.assertIn("JUCE: INVALID local path", output)
        self.assertIn("SkellCore: INVALID local path", output)

    def test_missing_cmake_is_not_ready_even_with_local_sources(self):
        juce = self.root / "JUCE"
        core = self.root / "SkellCore"
        self.make_juce(juce)
        self.make_core(core)

        ready, output = self.run_doctor(juce, core, cmake=None, git=None)
        self.assertFalse(ready)
        self.assertIn("cmake: NOT FOUND", output)
        self.assertIn("Dependency readiness: NOT READY", output)

    def test_cli_accepts_local_dependency_paths(self):
        juce = self.root / "JUCE"
        core = self.root / "SkellCore"
        self.make_juce(juce)
        self.make_core(core)
        with patch("skellforge.forge.shutil.which", side_effect=lambda name: "/usr/bin/" + name):
            with patch("builtins.print"):
                self.assertEqual(
                    main(["doctor", "--juce-path", str(juce), "--core-path", str(core)]),
                    0,
                )

if __name__ == "__main__":
    unittest.main()
