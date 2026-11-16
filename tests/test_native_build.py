import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skellforge.forge import build_native_pilot, ForgeError


class NativeBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sdk = self.root / 'native'
        source = self.sdk / 'native/vst3'
        source.mkdir(parents=True)
        (source / 'CMakeLists.txt').write_text('# fixture')

    @patch('skellforge.forge.windows_native_platform', return_value=True)
    @patch('skellforge.forge.subprocess.run')
    def test_build_runs_validator_audio_and_runtime_gates(self, run):
        build_native_pilot(self.sdk, self.root / 'build', 'mini')
        self.assertEqual(run.call_count, 3)
        self.assertIn('SkellNativeControlTests', run.call_args_list[1].args[0])
        command = run.call_args_list[2].args[0]
        self.assertIn('--no-tests=error', command)
        self.assertIn('SkellMiniOfficialValidator', command[-1])
        self.assertIn('SkellMiniBinaryAudio', command[-1])
        self.assertTrue(all(call.kwargs['check'] for call in run.call_args_list))

    @patch('skellforge.forge.windows_native_platform', return_value=True)
    @patch('skellforge.forge.subprocess.run')
    def test_failed_build_prevents_verification(self, run):
        run.side_effect = [None, subprocess.CalledProcessError(1, 'build')]
        with self.assertRaises(subprocess.CalledProcessError):
            build_native_pilot(self.sdk, self.root / 'build', 'mini')
        self.assertEqual(run.call_count, 2)

    @patch('skellforge.forge.windows_native_platform', return_value=True)
    @patch('skellforge.forge.subprocess.run')
    def test_invalid_inputs_do_not_launch_tools(self, run):
        for pilot, output in [('unknown', self.root / 'build'), ('mini', self.sdk), ('mini', self.root)]:
            with self.subTest(pilot=pilot, output=output), self.assertRaises(ForgeError):
                build_native_pilot(self.sdk, output, pilot)
        with self.assertRaises(ForgeError):
            build_native_pilot(self.sdk, self.root / 'build', 'mini', skelllang_source=self.root)
        run.assert_not_called()

    @patch('skellforge.forge.windows_native_platform', return_value=True)
    @patch('skellforge.forge.subprocess.run')
    def test_failed_validation_is_not_success(self, run):
        run.side_effect = [None, None, subprocess.CalledProcessError(1, 'ctest')]
        with self.assertRaises(subprocess.CalledProcessError):
            build_native_pilot(self.sdk, self.root / 'build', 'mini')
