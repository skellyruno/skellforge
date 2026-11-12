"""Strict SkellNative experimental VST3 x64 packaging/identity check."""
from __future__ import annotations

import argparse
from pathlib import Path

from skellforge.forge import ForgeError
from skellforge.local import check_pe_x64


def inspect(build: Path) -> tuple[Path, Path]:
    root = build.expanduser().resolve()
    if not root.is_dir():
        raise ForgeError("Missing SkellNative CMake build directory")
    bundles = sorted(p for p in root.rglob("*.vst3") if p.is_dir()
                     and p.name == "SkellNativeGain.vst3")
    if len(bundles) != 1:
        raise ForgeError(f"Expected exactly one SkellNativeGain VST3 bundle, got {len(bundles)}")
    bundle = bundles[0]
    if bundle.is_symlink() or any(p.is_symlink() for p in bundle.rglob("*")):
        raise ForgeError("Native VST3 bundle contains symlinks")
    binaries = sorted(p for p in bundle.rglob("*.vst3") if p.is_file())
    if len(binaries) != 1:
        raise ForgeError(f"Expected one native .vst3 PE binary, got {len(binaries)}")
    check_pe_x64(binaries[0])
    return bundle, binaries[0]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    args = parser.parse_args()
    try:
        bundle, binary = inspect(args.build)
        print(f"Verified standalone direct-VST3 bundle: {bundle}")
        print(f"Windows x64 PE32+ processor/controller: {binary}")
    except ForgeError as exc:
        parser.exit(1, f"Native VST3 verification failed: {exc}\n")
