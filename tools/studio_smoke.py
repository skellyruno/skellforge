"""CI smoke fixture: enable two real generated DSP stages and one UI text item.

Used only for a disposable generated CI plugin; normal Forge defaults remain
bypassed and audio-neutral.
"""
import sys
from pathlib import Path
from skellforge.studio import load_studio, save_studio, regenerate

if len(sys.argv) != 2:
    raise SystemExit("usage: python tools/studio_smoke.py <generated-project>")
project = Path(sys.argv[1]).resolve()
data = load_studio(project)
data["chain"].extend([
    {"id": "saturate_1", "type": "saturate", "enabled": True, "drive": 2.0},
    {"id": "lowpass_1", "type": "lowpass", "enabled": True, "cutoff_hz": 8000.0},
])
data["components"].append({
    "id": "smoke_label", "type": "text",
    "text": "SKELL / DSP CHECK",
    "x": 20, "y": 264, "w": 210, "h": 24,
})
save_studio(project, data)
changed = regenerate(project)
assert "ForgeGraph.h" in changed and "ForgeUI.h" in changed
print("Studio DSP+UI fixture exported:", changed)
