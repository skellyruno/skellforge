"""Performance measurement infrastructure should stay nonintrusive."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class SkellDrawUiPerformanceTests(unittest.TestCase):
    def test_gui_profiler_is_test_only(self):
        cm=(ROOT/"native/vst3/CMakeLists.txt").read_text(encoding="utf-8")
        h=(ROOT/"native/vst3/Source/SkellDrawWin32.h").read_text(encoding="utf-8")
        src=(ROOT/"native/vst3/Source/SkellDrawWin32.cpp").read_text(encoding="utf-8")
        painter=(ROOT/"native/skelldraw/include/SkellDraw/Win32Painter.h").read_text(encoding="utf-8")
        assert "SKELLDRAW_PROFILE=1" in cm
        assert "target_compile_definitions(SkellNativeGain PRIVATE SKELLDRAW_PROFILE" not in cm
        for required in ("UiProfileStats","redrawRequests","backBufferCreates"):
            self.assertIn(required,h)
        for required in ("QueryPerformanceCounter","QueryPerformanceFrequency",
                         "profile_.paintCalls","profile_.timerTicks"):
            self.assertIn(required,src)
        self.assertIn("LabelFontCache",painter)
        self.assertIn("KnobPens",painter)
        self.assertIn("100 unchanged meter/knob timer ticks cause ZERO redraws",
            (ROOT/"native/vst3/tests/SkellDrawUiSmoke.cpp").read_text())

    def test_fl_cpu_script_is_read_only_and_not_dsp_benchmark(self):
        script=(ROOT/"native/vst3/tools/Measure-FLStudioProcess.ps1").read_text()
        docs=(ROOT/"docs/SKELLDRAW_PROFILING.md").read_text()
        for token in ("Get-Process","TotalProcessorTime","Export-Csv",
                      "LogicalCPUs","NativeClosed","NativeOpen","ProcessName"):
            self.assertIn(token,script)
        for forbidden in ("Remove-Item","Set-Content","Stop-Process",
                          "Start-Process","Program Files/Common Files"):
            self.assertNotIn(forbidden,script)
        self.assertIn("NOT an isolated VST3 CPU measurement",docs)
        self.assertIn("no QPC instrumentation",docs)

if __name__=="__main__":
    unittest.main()
