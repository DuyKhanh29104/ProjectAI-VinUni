#!/usr/bin/env python3
"""Safely remove Label Guardian's local E2E object artifacts.

PostgreSQL records are intentionally left untouched. Use a dedicated test
database and the test fixtures when database cleanup is required.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _is_within_e2e(path: Path) -> bool:
    return path.resolve().is_relative_to((Path("data") / "e2e").resolve())


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove local Label Guardian E2E data.")
    parser.add_argument("--object-root", type=Path, default=Path("data/e2e/objects"))
    parser.add_argument("--yes", action="store_true", help="Confirm deletion.")
    arguments = parser.parse_args()
    if not _is_within_e2e(arguments.object_root):
        raise SystemExit("Refusing: cleanup targets must be inside data/e2e.")
    if not arguments.yes:
        raise SystemExit("Pass --yes to delete local E2E data.")
    if arguments.object_root.exists():
        shutil.rmtree(arguments.object_root)
    print("Removed Label Guardian local E2E objects. PostgreSQL records were not changed.")


if __name__ == "__main__":
    main()
