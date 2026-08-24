import json
from pathlib import Path

import pytest

from src.services.ingestion.kitti_playwright_auth import (
    KittiBrowserAuthError,
    cookie_header_from_playwright_storage,
    cvlibs_cookie_pairs_from_playwright_storage,
)


def test_builds_cookie_header_from_playwright_storage(tmp_path: Path):
    storage = tmp_path / "cookies.json"
    storage.write_text(
        json.dumps(
            {
                "cookies": [
                    {"name": "session", "value": "abc", "domain": ".cvlibs.net"},
                    {"name": "other", "value": "ignored", "domain": "example.test"},
                    {"name": "user", "value": "hung", "domain": "www.cvlibs.net"},
                ]
            }
        )
    )

    assert cvlibs_cookie_pairs_from_playwright_storage(storage) == ["session=abc", "user=hung"]
    assert cookie_header_from_playwright_storage(storage) == "session=abc; user=hung"


def test_cookie_header_reports_missing_cvlibs_cookies(tmp_path: Path):
    storage = tmp_path / "cookies.json"
    storage.write_text(json.dumps({"cookies": [{"name": "x", "value": "1", "domain": "example.test"}]}))

    with pytest.raises(KittiBrowserAuthError, match="No CVLIBS cookies"):
        cookie_header_from_playwright_storage(storage)
