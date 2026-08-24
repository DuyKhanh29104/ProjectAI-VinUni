#!/usr/bin/env python3
"""Open a browser to log in to KITTI/CVLIBS and save Playwright cookies."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.ingestion.kitti_playwright_auth import KittiBrowserAuthError, save_kitti_browser_session  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Save KITTI/CVLIBS browser cookies for automated ingestion.")
    parser.add_argument("--cookie-json", type=Path, default=Path("data/secrets/kitti_cookies.json"))
    parser.add_argument("--headless", action="store_true")
    arguments = parser.parse_args()
    try:
        save_kitti_browser_session(arguments.cookie_json, headless=arguments.headless)
    except KittiBrowserAuthError as error:
        parser.error(str(error))
    print(f"Saved KITTI/CVLIBS cookies to {arguments.cookie_json.resolve()}")


if __name__ == "__main__":
    main()
