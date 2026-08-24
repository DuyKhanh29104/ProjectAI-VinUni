"""Playwright helpers for reusing an authenticated KITTI CVLIBS browser session."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

KITTI_LOGIN_URL = "https://www.cvlibs.net/datasets/kitti/user_login.php"
CVLIBS_DOMAINS = ("cvlibs.net", "www.cvlibs.net")


class KittiBrowserAuthError(RuntimeError):
    """Raised when browser auth cannot be prepared or read."""


def cvlibs_cookie_pairs_from_playwright_storage(storage_state_path: Path) -> list[str]:
    """Return CVLIBS cookie pairs from Playwright storage_state JSON."""
    if not storage_state_path.is_file():
        raise KittiBrowserAuthError(f"Playwright cookie storage does not exist: {storage_state_path}")
    payload = json.loads(storage_state_path.read_text(encoding="utf-8"))
    pairs: list[str] = []
    for cookie in payload.get("cookies", []):
        domain = str(cookie.get("domain", "")).lstrip(".")
        if domain in CVLIBS_DOMAINS or domain.endswith(".cvlibs.net"):
            name = cookie.get("name")
            value = cookie.get("value")
            if name and value is not None:
                pairs.append(f"{name}={value}")
    return pairs


def cookie_header_from_playwright_storage(storage_state_path: Path) -> str:
    """Convert Playwright storage_state JSON into a Cookie header for CVLIBS."""
    pairs = cvlibs_cookie_pairs_from_playwright_storage(storage_state_path)
    if not pairs:
        raise KittiBrowserAuthError(
            f"No CVLIBS cookies found in {storage_state_path}. Open the browser login flow and log in first."
        )
    return "; ".join(pairs)


def save_kitti_browser_session(
    storage_state_path: Path,
    *,
    login_url: str = KITTI_LOGIN_URL,
    headless: bool = False,
    email: str | None = None,
    password: str | None = None,
) -> None:
    """Open CVLIBS, optionally fill credentials, then save its reusable session."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
    except ImportError as error:
        raise KittiBrowserAuthError(
            "Playwright is not installed. Run `pip install -e '.[ingestion]'` and `playwright install chromium`."
        ) from error

    storage_state_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context_kwargs: dict[str, Any] = {}
        if storage_state_path.is_file():
            context_kwargs["storage_state"] = str(storage_state_path)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.goto(login_url, wait_until="domcontentloaded")
        login_completed = False
        if email and password:
            email_field = page.locator("input[type='email'], input[name*='email' i]").first
            password_field = page.locator("input[type='password']").first
            if email_field.count() and password_field.count():
                email_field.fill(email)
                password_field.fill(password)
                submit_button = page.locator("input[type='submit'], button[type='submit']").first
                if submit_button.count():
                    submit_button.click()
                    page.wait_for_load_state("domcontentloaded")
                    login_completed = True
            else:
                print("Could not identify the CVLIBS login fields; complete login in the browser window.")
        if not login_completed:
            print("Log in to KITTI/CVLIBS in the browser window, then return here and press Enter.")
            input("Press Enter after login is complete...")
        context.storage_state(path=str(storage_state_path))
        browser.close()
    pairs = cvlibs_cookie_pairs_from_playwright_storage(storage_state_path)
    if not pairs:
        raise KittiBrowserAuthError(
            "Browser session was saved, but it did not contain CVLIBS cookies. "
            "Make sure the login completed on cvlibs.net before pressing Enter."
        )
    print(f"Saved {len(pairs)} CVLIBS cookie(s).")
