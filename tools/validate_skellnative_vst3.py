"""Run the OFFICIAL Steinberg SDK validator against the native gain bundle."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from skellforge.forge import ForgeError
from tools.check_skellnative_vst3 import inspect


def find_validator(build: Path) -> Path:
    matches = sorted(p for p in Path(build).resolve().rglob("validator.exe")
                     if p.is_file() and not p.is_symlink())
    if len(matches) != 1:
        raise ForgeError(
            f"Expected one Steinberg validator.exe, found {len(matches)}. "
            "Build target validator with SMTG_ENABLE_VST3_HOSTING_EXAMPLES=ON.")
    return matches[0]


def run_validator(build: Path, timeout: int = 180) -> None:
    bundle, binary = inspect(build)
    validator = find_validator(build)
    print(f"Official Steinberg validator: {validator}", flush=True)
    print(f"Target direct-SDK VST3: {bundle}", flush=True)
    try:
        completed = subprocess.run(
            [str(validator), str(bundle)], text=True, encoding="utf-8",
            errors="replace", capture_output=True, timeout=timeout,
            check=False, cwd=str(Path(build).resolve()))
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise ForgeError(f"Could not complete official SDK validation: {exc}") from exc
    print(completed.stdout[-24000:], flush=True)
    if completed.stderr:
        print(completed.stderr[-5000:], flush=True)
    if completed.returncode != 0:
        raise ForgeError(
            f"Steinberg VST3 validator returned {completed.returncode}. "
            "Do not distribute this plugin until host-contract failures are fixed.")
    print("PASS: Steinberg official VST3 validator completed without failures",
          flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parsed = parser.parse_args()
    try:
        run_validator(parsed.build)
    except ForgeError as exc:
        parser.exit(1, f"Steinberg validation failed: {exc}\n")
