"""Regression tests for validation, audit, build-path and packaging hardening."""
import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from skellforge import forge
from skellforge.audit import _strip_cpp_comments, audit_project, strip_cmake_comments
from skellforge.forge import (
    ForgeError, build_project, create_project, identity, main, package_project,
    validate_project,
)

ROOT = Path(forge.__file__).resolve().parents[1]
BUNDLE_REL = Path("Skell Pulse.vst3") / "Contents" / "x86_64-win" / "Skell Pulse.vst3"


class ProjectCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "skell-pulse"

    def make(self, code="Sf01"):
        return create_project("Skell Pulse", self.project, code)

    def replace_in_sources(self, old, new):
        """Textually replace `old` in every file under Source/ (a project-wide refactor)."""
        for file in sorted((self.project / "Source").iterdir()):
            file.write_text(file.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

    def add_file(self, relative, text):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def edit(self, relative, old, new):
        path = self.project / relative
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text, f"test precondition: {old!r} missing from {relative}")
        path.write_text(text.replace(old, new), encoding="utf-8")

    def fake_bundle(self, *parts):
        binary = self.project.joinpath("build", "SkellPulse_artefacts", *parts) / BUNDLE_REL
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"surrogate binary")


class IdentityRulesTests(unittest.TestCase):
    def test_name_length_and_trailing_space(self):
        longest = "a " * 39 + "ab"  # exactly 80 characters, 41-character slug
        self.assertEqual(len(longest), 80)
        self.assertEqual(identity("Ab", "Sf01")["target"], "Ab")
        self.assertEqual(identity(longest, "Sf01")["name"], longest)
        self.assertEqual(identity("Skell-", "Sf01")["name"], "Skell-")
        for name in (longest + "c", "A", "Skell Pulse ", "Skell Pulse\n", " Skell"):
            with self.subTest(name=name), self.assertRaises(ForgeError):
                identity(name, "Sf01")

    def test_windows_reserved_file_names_rejected(self):
        for name in ("Aux", "CON", "nul", "Prn", "Com1", "lpt9"):
            with self.subTest(name=name), self.assertRaisesRegex(ForgeError, "reserved Windows"):
                identity(name, "Sf01")
        for name in ("Aux Send", "Console", "Com10", "Nullify"):
            with self.subTest(name=name):
                self.assertEqual(identity(name, "Sf01")["name"], name)

    def test_known_code_catalog_is_well_formed(self):
        codes = json.loads((ROOT / "config" / "known_codes.json").read_text(encoding="utf-8"))["codes"]
        self.assertTrue(codes)
        for code, owner in codes.items():
            with self.subTest(code=code):
                self.assertRegex(code, r"[A-Za-z0-9]{4}\Z")
                self.assertTrue(owner.strip())
        folded = [code.casefold() for code in codes]
        self.assertEqual(len(folded), len(set(folded)), "codes differing only by case collide")


class ValidateHardeningTests(ProjectCase):
    def test_malformed_manifests_are_reported_not_crashed(self):
        cases = (
            ("skellforge.json", "[]", "JSON object"),
            ("skellworld.json", "[]", "JSON object"),
            ("skellforge.json", "null", "JSON object"),
            ("skellforge.json", "{", "Invalid project manifest"),
        )
        for filename, payload, message in cases:
            with self.subTest(filename=filename, payload=payload):
                shutil.rmtree(self.project, ignore_errors=True)
                self.make()
                (self.project / filename).write_text(payload, encoding="utf-8")
                with self.assertRaisesRegex(ForgeError, message):
                    validate_project(self.project)

    def test_wrong_field_types_are_reported_not_crashed(self):
        for key, value in (("name", 5), ("plugin_code", None), ("core_revision", 7),
                           ("core_repo", ["x"]), ("parameter_ids", "gain_db"),
                           ("parameter_ids", [1, 2])):
            with self.subTest(key=key, value=value):
                shutil.rmtree(self.project, ignore_errors=True)
                self.make()
                path = self.project / "skellforge.json"
                manifest = json.loads(path.read_text(encoding="utf-8"))
                manifest[key] = value
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(ForgeError, "Invalid skellforge.json"):
                    validate_project(self.project)

    def test_cli_reports_malformed_manifest_with_exit_code_1(self):
        self.make()
        (self.project / "skellforge.json").write_text("[]", encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(main(["validate", str(self.project)]), 1)
        self.assertIn("SkellForge error", err.getvalue())

    def test_parameter_id_renamed_everywhere_is_detected(self):
        self.make()
        self.replace_in_sources('"gain_db"', '"renamed_gain"')
        with self.assertRaisesRegex(ForgeError, "gain_db"):
            validate_project(self.project)

    def test_commented_out_parameter_id_does_not_count(self):
        self.make()
        self.replace_in_sources('"gain_db"', '0 /* "gain_db" */')
        with self.assertRaisesRegex(ForgeError, "gain_db"):
            validate_project(self.project)

    def test_parameter_id_only_in_build_output_does_not_count(self):
        self.make()
        self.replace_in_sources('"gain_db"', '"renamed_gain"')
        self.add_file("build/generated/stale.cpp", 'auto old = "gain_db";\n')
        with self.assertRaisesRegex(ForgeError, "gain_db"):
            validate_project(self.project)

    def test_refactoring_the_id_into_a_constant_is_not_an_error(self):
        # A valid refactor must not block validate/build/package.
        self.make()
        self.replace_in_sources('"gain_db"', "ids::gain")
        self.add_file("Source/ParamIds.h",
                      'namespace ids { inline constexpr const char* gain = "gain_db"; }\n')
        self.assertEqual(validate_project(self.project)["parameter_ids"], ["gain_db"])

    def test_id_declared_outside_source_folder_or_in_inl_file_is_not_an_error(self):
        for relative in ("Parameters/ids.cpp", "Source/ids.inl", "src/deep/er/ids.hpp"):
            with self.subTest(relative=relative):
                shutil.rmtree(self.project, ignore_errors=True)
                self.make()
                self.replace_in_sources('"gain_db"', "ids::gain")
                self.add_file(relative, 'inline constexpr const char* gain = "gain_db";\n')
                validate_project(self.project)

    def test_parameter_ids_with_unusual_characters_are_matched_literally(self):
        self.make()
        path = self.project / "skellforge.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["parameter_ids"] = ["gain_db", "gain db", "a.b-c"]
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ForgeError, "a.b-c, gain db"):
            validate_project(self.project)
        self.add_file("Source/extra.h", 'auto a = "gain db", b = "a.b-c";\n')
        validate_project(self.project)

    def test_oversized_or_unreadable_files_make_the_scan_inconclusive(self):
        self.make()
        self.replace_in_sources('"gain_db"', '"renamed_gain"')
        self.add_file("Source/huge.cpp", "a" * (1024 * 1024 + 1))
        self.assertEqual(validate_project(self.project)["plugin_code"], "Sf01")

    def test_absurdly_nested_json_is_reported_not_crashed(self):
        self.make()
        (self.project / "skellforge.json").write_text("[" * 200000, encoding="utf-8")
        with self.assertRaisesRegex(ForgeError, "Invalid project manifest"):
            validate_project(self.project)

    def test_cmake_comment_markers_inside_strings_cannot_hide_standalone(self):
        self.make()
        self.edit("CMakeLists.txt", "FORMATS VST3",
                  'FORMATS VST3\n  EXTRA "a #[[ b" Standalone EXTRA2 "]]"')
        with self.assertRaisesRegex(ForgeError, "Only the Windows VST3"):
            validate_project(self.project)

    def test_quoted_core_repository_url_is_accepted(self):
        self.make()
        repo = json.loads((self.project / "skellforge.json").read_text(encoding="utf-8"))["core_repo"]
        self.edit("CMakeLists.txt", f"GIT_REPOSITORY {repo}", f'GIT_REPOSITORY "{repo}"')
        validate_project(self.project)

    def test_adding_a_parameter_is_allowed(self):
        self.make()
        path = self.project / "Source" / "PluginProcessor.cpp"
        path.write_text(path.read_text(encoding="utf-8") +
                        '\nstatic const auto extra = juce::ParameterID{"extra_hz", 1};\n',
                        encoding="utf-8")
        self.assertEqual(validate_project(self.project)["parameter_ids"], ["gain_db"])

    def test_file_limit_cannot_prove_a_parameter_is_missing(self):
        self.make()
        self.replace_in_sources('"gain_db"', '"renamed_gain"')
        with patch("skellforge.forge.PARAMETER_SCAN_LIMIT", 1):
            self.assertEqual(validate_project(self.project)["plugin_code"], "Sf01")
        with self.assertRaisesRegex(ForgeError, "gain_db"):  # and without the limit it is proven
            validate_project(self.project)

    def test_cmake_plugin_code_must_match_whole_token(self):
        self.make()
        self.edit("CMakeLists.txt", "PLUGIN_CODE Sf01", "PLUGIN_CODE Sf01x")
        with self.assertRaisesRegex(ForgeError, "CMake identity"):
            validate_project(self.project)

    def test_commented_cmake_line_does_not_satisfy_identity_check(self):
        self.make()
        self.edit("CMakeLists.txt", "PLUGIN_CODE Sf01", "PLUGIN_CODE Zzzz\n  # PLUGIN_CODE Sf01")
        with self.assertRaisesRegex(ForgeError, "CMake identity"):
            validate_project(self.project)

    def test_core_repository_mismatch_is_detected(self):
        self.make()
        path = self.project / "skellforge.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["core_repo"] = "https://github.com/someone/else.git"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ForgeError, "GIT_REPOSITORY"):
            validate_project(self.project)

    def test_a_comment_mentioning_standalone_is_not_a_standalone_build(self):
        self.make()
        self.edit("CMakeLists.txt", "FORMATS VST3", "FORMATS VST3  # Standalone is intentionally off")
        self.assertEqual(validate_project(self.project)["formats"], ["VST3"])

    def test_real_standalone_still_rejected(self):
        self.make()
        self.edit("CMakeLists.txt", "FORMATS VST3", "FORMATS VST3 Standalone")
        with self.assertRaisesRegex(ForgeError, "Only the Windows VST3"):
            validate_project(self.project)

    def test_manifests_use_unix_newlines(self):
        self.make()
        for name in ("skellforge.json", "skellworld.json"):
            self.assertNotIn(b"\r", (self.project / name).read_bytes())


class BuildTests(ProjectCase):
    def run_build(self, **kwargs):
        with patch("skellforge.forge.sys.platform", "win32"), \
                patch("skellforge.forge.shutil.which", return_value="cmake"), \
                patch("skellforge.forge.subprocess.run") as run:
            build_project(self.project, **kwargs)
        return run

    def test_default_build_commands(self):
        self.make()
        run = self.run_build()
        configure, build = (call.args[0] for call in run.call_args_list)
        self.assertEqual(configure[:2], ["cmake", "-S"])
        self.assertIn("x64", configure)
        self.assertFalse([a for a in configure if a.startswith("-D")])
        self.assertEqual(build[-4:], ["--config", "Release", "--parallel", "2"])

    def test_skellcore_repo_root_layout_is_accepted(self):
        self.make()
        core = self.root / "skellcore-vst-template"
        (core / "SkellCore").mkdir(parents=True)
        (core / "SkellCore" / "CMakeLists.txt").write_text("# stub\n")
        run = self.run_build(core_path=core)
        self.assertIn(f"-DSKELLCORE_PATH={core.resolve()}", run.call_args_list[0].args[0])

    def test_skellcore_library_folder_layout_is_accepted(self):
        self.make()
        core = self.root / "SkellCore"
        core.mkdir()
        (core / "CMakeLists.txt").write_text("# stub\n")
        run = self.run_build(core_path=core)
        self.assertIn(f"-DSKELLCORE_PATH={core.resolve()}", run.call_args_list[0].args[0])

    def test_bad_local_paths_fail_before_cmake_runs(self):
        self.make()
        empty = self.root / "empty"
        empty.mkdir()
        for option, kwargs in (("JUCE_PATH", {"juce_path": empty}),
                               ("SKELLCORE_PATH", {"core_path": empty})):
            with self.subTest(option=option):
                with patch("skellforge.forge.sys.platform", "win32"), \
                        patch("skellforge.forge.shutil.which", return_value="cmake"), \
                        patch("skellforge.forge.subprocess.run") as run:
                    with self.assertRaisesRegex(ForgeError, option):
                        build_project(self.project, **kwargs)
                run.assert_not_called()

    def test_missing_cmake_is_explicit(self):
        self.make()
        with patch("skellforge.forge.sys.platform", "win32"), \
                patch("skellforge.forge.shutil.which", return_value=None):
            with self.assertRaisesRegex(ForgeError, "CMake is not installed"):
                build_project(self.project)


class PackageHardeningTests(ProjectCase):
    def test_stale_debug_bundle_does_not_block_release_packaging(self):
        self.make()
        self.fake_bundle("Release", "VST3")
        self.fake_bundle("Debug", "VST3")
        with zipfile.ZipFile(package_project(self.project)) as archive:
            self.assertEqual(archive.namelist(), [BUNDLE_REL.as_posix()])

    def test_single_config_layout_without_config_folder(self):
        self.make()
        self.fake_bundle("VST3")
        with zipfile.ZipFile(package_project(self.project)) as archive:
            self.assertEqual(archive.namelist(), [BUNDLE_REL.as_posix()])

    def test_failed_integrity_check_leaves_no_partial_zip(self):
        self.make()
        self.fake_bundle("Release", "VST3")
        out = self.root / "out.zip"
        with patch.object(zipfile.ZipFile, "testzip", return_value="corrupt-member"):
            with self.assertRaisesRegex(ForgeError, "integrity"):
                package_project(self.project, out)
        self.assertFalse(out.exists())

    def test_interrupted_write_leaves_no_partial_zip(self):
        self.make()
        self.fake_bundle("Release", "VST3")
        out = self.root / "out.zip"
        with patch.object(zipfile.ZipFile, "write", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                package_project(self.project, out)
        self.assertFalse(out.exists())

    def test_failure_to_delete_the_partial_zip_does_not_mask_the_real_error(self):
        self.make()
        self.fake_bundle("Release", "VST3")
        out = self.root / "out.zip"
        with patch.object(zipfile.ZipFile, "write", side_effect=OSError("disk full")), \
                patch("pathlib.Path.unlink", side_effect=PermissionError("locked")):
            with self.assertRaisesRegex(OSError, "disk full"):
                package_project(self.project, out)

    def test_existing_output_file_is_never_touched(self):
        self.make()
        self.fake_bundle("Release", "VST3")
        out = self.root / "keep.zip"
        out.write_bytes(b"precious")
        with self.assertRaisesRegex(ForgeError, "overwrite"):
            package_project(self.project, out)
        self.assertEqual(out.read_bytes(), b"precious")


class AuditAccuracyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        (self.path / "Source").mkdir()

    def cmake(self, text):
        (self.path / "CMakeLists.txt").write_text(text, encoding="utf-8")

    def source(self, text, name="P.cpp"):
        (self.path / "Source" / name).write_text(text, encoding="utf-8")

    def test_multiline_formats_detect_standalone(self):
        self.cmake("juce_add_plugin(Old\n  FORMATS\n    VST3\n    Standalone\n"
                   "  PLUGIN_CODE Old1\n  BUNDLE_ID \"x.y\")\n")
        report = audit_project(self.path)
        self.assertEqual(report["formats_detected"], ["VST3", "Standalone"])
        self.assertTrue(any("Standalone" in w for w in report["warnings"]))

    def test_commented_formats_are_ignored(self):
        self.cmake("juce_add_plugin(Old FORMATS VST3\n  PLUGIN_CODE Old1 BUNDLE_ID \"x.y\")\n"
                   "# FORMATS AU Standalone\n#[[ FORMATS AAX ]]\n")
        self.assertEqual(audit_project(self.path)["formats_detected"], ["VST3"])

    def test_keys_on_the_same_line_are_found(self):
        self.cmake('juce_add_plugin(Old FORMATS VST3 PLUGIN_CODE Ab12 BUNDLE_ID "x.y")\n')
        report = audit_project(self.path)
        self.assertEqual((report["plugin_code"], report["bundle_id"]), ("Ab12", "x.y"))

    def test_manufacturer_code_is_not_mistaken_for_plugin_code(self):
        self.cmake("juce_add_plugin(Old\n  PLUGIN_MANUFACTURER_CODE SkAu\n  FORMATS VST3)\n")
        report = audit_project(self.path)
        self.assertIsNone(report["plugin_code"])
        self.assertTrue(any("plugin code not found" in w for w in report["warnings"]))

    def test_formats_variants_are_all_understood(self):
        for formats, expected in (("${F} Standalone", ["Standalone"]),
                                  ("VST3;Standalone", ["VST3", "Standalone"]),
                                  ('"VST3;Standalone"', ["VST3", "Standalone"]),
                                  ("VST3\n    AU", ["VST3", "AU"]),
                                  ("${F}", [])):
            with self.subTest(formats=formats):
                self.cmake(f"juce_add_plugin(Old FORMATS {formats} PRODUCT_NAME Standalone)\n")
                self.assertEqual(audit_project(self.path)["formats_detected"], expected)

    def test_identity_keywords_are_read_from_the_plugin_call_only(self):
        self.cmake('message(STATUS "PLUGIN_CODE is set below")\nset(PLUGIN_CODE Zzzz)\n'
                   'if(DEFINED BUNDLE_ID AND TRUE)\nendif()\n'
                   'juce_add_plugin(Old FORMATS VST3\n  PLUGIN_CODE Ab12 (x)\n  BUNDLE_ID "x.y")\n')
        report = audit_project(self.path)
        self.assertEqual((report["plugin_code"], report["bundle_id"]), ("Ab12", "x.y"))

    def test_comment_markers_in_comments_or_strings_do_not_eat_real_code(self):
        self.cmake('# note about #[[ nesting\njuce_add_plugin(Old FORMATS VST3 PLUGIN_CODE Ab12 '
                   'BUNDLE_ID "x.y")\n# end ]]\n')
        report = audit_project(self.path)
        self.assertTrue(report["juce_target_detected"])
        self.assertEqual(report["plugin_code"], "Ab12")
        kept = strip_cmake_comments('COMPANY_NAME "Skell #[[ Audio"\nFORMATS Standalone\nX "]]"\n')
        self.assertIn("FORMATS Standalone", kept)

    def test_strip_cmake_comments_keeps_hash_inside_strings(self):
        self.assertEqual(strip_cmake_comments('BUNDLE_ID "a#b" # note'), 'BUNDLE_ID "a#b" ')
        self.assertEqual(strip_cmake_comments('a #[==[ x ]] y ]==] b\n[[ # kept ]] c'),
                         'a   b\n[[ # kept ]] c')

    def test_cpp_comment_stripping_understands_literals(self):
        text = ('char q = \'"\'; // trailing "bogus"\nauto a = ParameterID{"real", 1};\n'
                'auto s = R"x(a " // not a comment /* nor this )x"; auto b = ParameterID{"after", 1};\n'
                "int n = 1'000'000; /* c */ f(\"k\"); const char* u = \"http://x\"; g(\"m\");\n")
        stripped = _strip_cpp_comments(text)
        for kept in ('ParameterID{"real", 1}', "// not a comment /* nor this", 'ParameterID{"after", 1}',
                     'f("k")', 'g("m")', '"http://x"'):
            self.assertIn(kept, stripped)
        for dropped in ("bogus", "/* c */"):
            self.assertNotIn(dropped, stripped)

    def test_unterminated_comments_are_handled_in_linear_time(self):
        started = time.monotonic()
        self.assertEqual(_strip_cpp_comments("a /* " * 200000)[:3], "a  ")
        self.assertEqual(strip_cmake_comments("x #[[ " * 200000)[:3], "x  ")
        self.assertLess(time.monotonic() - started, 5.0)

    def test_legacy_and_modern_parameter_ids_are_found_but_comments_are_not(self):
        self.cmake("juce_add_plugin(Old FORMATS VST3)\n")
        self.source(
            'layout.add(std::make_unique<juce::AudioParameterFloat>("cutoff", "Cutoff", 20.f, 2e4f, 1e3f));\n'
            'v.push_back(std::make_unique<juce::AudioParameterBool>(juce::ParameterID("bypass", 1), "B", false));\n'
            'auto url = "http://example.test"; layout.add(std::make_unique<juce::AudioParameterInt>("real", "R", 0, 1, 0));\n'
            '// layout.add(std::make_unique<juce::AudioParameterFloat>("line_commented", "x", 0, 1, 0));\n'
            '/* juce::ParameterID{"block_commented", 1} */\n')
        self.assertEqual(audit_project(self.path)["parameter_ids_detected"],
                         ["bypass", "cutoff", "real"])

    def test_no_parameters_found_is_called_out(self):
        self.cmake("juce_add_plugin(Old FORMATS VST3)\n")
        self.source("int main() {}\n")
        self.assertTrue(any("No parameter IDs" in w for w in audit_project(self.path)["warnings"]))

    def test_truncated_scan_is_reported(self):
        self.cmake("juce_add_plugin(Old FORMATS VST3)\n")
        for index in range(161):
            self.source("// empty\n", f"f{index:03d}.cpp")
        warnings = audit_project(self.path)["warnings"]
        self.assertTrue(any("scan stopped" in w for w in warnings))

    def test_oversized_source_is_reported(self):
        self.cmake("juce_add_plugin(Old FORMATS VST3)\n")
        self.source("a" * (1024 * 1024 + 1), "huge.cpp")
        warnings = audit_project(self.path)["warnings"]
        self.assertTrue(any("over 1 MiB" in w for w in warnings))


class CliAndTemplateTests(ProjectCase):
    def test_old_python_gets_a_clear_message_not_a_traceback(self):
        err = io.StringIO()
        with patch("skellforge.forge.MIN_PYTHON", (99, 0)), contextlib.redirect_stderr(err):
            self.assertEqual(main(["doctor"]), 1)
        self.assertIn("Python 99.0+ is required", err.getvalue())

    def test_doctor_reports_python_requirement(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["doctor"]), 0)
        self.assertIn("Python 3.10+ required: ok", out.getvalue())

    def test_generated_gitignore_excludes_package_zip(self):
        self.make()
        self.assertIn("/SkellForge-*.zip", (self.project / ".gitignore").read_text())


@unittest.skipIf(sys.platform == "win32" or not shutil.which("cmake")
                 or not (shutil.which("c++") or shutil.which("g++"))
                 or not (shutil.which("cc") or shutil.which("gcc")),
                 "needs cmake and a C++ compiler on a non-Windows host (Windows is covered by the smoke build)")
class GeneratedCMakeConfigureTests(ProjectCase):
    """Configure the generated project against stub JUCE/SkellCore trees.

    This exercises the dependency-path logic only; it does not build JUCE or the plugin.
    """

    def setUp(self):
        super().setUp()
        juce = self.root / "juce"
        juce.mkdir()
        (juce / "CMakeLists.txt").write_text(
            "function(juce_add_plugin target)\n  add_library(${target} MODULE)\nendfunction()\n"
            "function(juce_generate_juce_header target)\nendfunction()\n"
            "foreach(n juce_audio_utils juce_audio_processors juce_gui_extra)\n"
            "  add_library(${n} INTERFACE)\n  add_library(juce::${n} ALIAS ${n})\nendforeach()\n")
        self.juce = juce
        self.core_stub = ("add_library(skdsp INTERFACE)\nadd_library(skui INTERFACE)\n"
                          "add_library(SkellCore::DSP ALIAS skdsp)\nadd_library(SkellCore::UI ALIAS skui)\n")
        self.make()

    def configure(self, *definitions):
        build = self.root / f"build{len(list(self.root.glob('build*')))}"
        # -DWIN32=1 only gets past the template's Windows-only guard on this host.
        return subprocess.run(["cmake", "-S", str(self.project), "-B", str(build), "-DWIN32=1",
                               *definitions], capture_output=True, text=True)

    def core(self, *subdir):
        path = self.root.joinpath("core", *subdir)
        path.mkdir(parents=True)
        (path / "CMakeLists.txt").write_text(self.core_stub)
        return self.root / "core"

    def test_repo_root_and_library_layouts_configure(self):
        for layout in ((), ("SkellCore",)):
            with self.subTest(layout=layout):
                shutil.rmtree(self.root / "core", ignore_errors=True)
                result = self.configure(f"-DJUCE_PATH={self.juce}", f"-DSKELLCORE_PATH={self.core(*layout)}")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_bad_juce_path_fails_instead_of_downloading(self):
        # "OFF", "0" and "NO" are false constants to a plain if(VAR); they must still be errors.
        for bad in (str(self.root / "nope"), "OFF", "0", "NO"):
            with self.subTest(juce_path=bad):
                result = self.configure(f"-DJUCE_PATH={bad}", f"-DSKELLCORE_PATH={self.core_once()}")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("JUCE_PATH does not contain", result.stderr)

    def test_bad_skellcore_path_fails_instead_of_downloading(self):
        for bad in (str(self.root / "nope"), "OFF", "0", "NO"):
            with self.subTest(skellcore_path=bad):
                result = self.configure(f"-DJUCE_PATH={self.juce}", f"-DSKELLCORE_PATH={bad}")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("SKELLCORE_PATH must contain", result.stderr)

    def core_once(self):
        """A valid SkellCore stub, created on first use only."""
        return self.root / "core" if (self.root / "core").is_dir() else self.core()


if __name__ == "__main__":
    unittest.main()
