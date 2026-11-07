#!/usr/bin/env python3
"""Prepare Saturn's mirrored build output tree before Make generates files.

Some Makefile rules write generated files directly into build/us_pc/<source-dir>
without creating the parent directory first. Mirror every source directory so
parallel builds do not fail on missing output folders.
"""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "build" / "us_pc"
SKIP = {".git", "build", ".github", "__pycache__", ".venv", "venv", "node_modules"}

def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    created = 0

    for current, dirs, _files in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        source_dir = Path(current)
        relative = source_dir.relative_to(ROOT)

        # The repository root maps to build/us_pc itself.
        target_dir = OUTPUT / relative
        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
            created += 1

    # A few generated headers live here even if no matching source folder exists.
    (OUTPUT / "include").mkdir(parents=True, exist_ok=True)
    print(f"Prepared Saturn build output tree: {OUTPUT} ({created} directories created)")

if __name__ == "__main__":
    main()
