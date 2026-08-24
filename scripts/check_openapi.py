"""Detect drift between FastAPI's generated OpenAPI schema and its snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from difflib import unified_diff
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Settings  # noqa: E402
from src.main import create_app  # noqa: E402

OPENAPI_SNAPSHOT = PROJECT_ROOT / "docs" / "openapi.json"


def generate_openapi_document() -> dict[str, Any]:
    """Generate a deterministic schema without reading developer-local .env values."""
    settings = Settings(app_env="test", _env_file=None)
    document = create_app(settings=settings).openapi()
    normalize_openapi_document(document)
    return document


def normalize_openapi_document(document: dict[str, Any]) -> None:
    """Remove environment-dependent details from generated framework schemas."""
    validation_error = (
        document.get("components", {})
        .get("schemas", {})
        .get("ValidationError", {})
    )
    properties = validation_error.get("properties")
    if isinstance(properties, dict):
        properties.pop("ctx", None)
        properties.pop("input", None)
    required = validation_error.get("required")
    if isinstance(required, list):
        validation_error["required"] = [item for item in required if item not in {"ctx", "input"}]


def render_openapi_document(document: dict[str, Any]) -> str:
    """Serialize OpenAPI consistently for reviewable Git diffs."""
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Update docs/openapi.json instead of checking it.",
    )
    args = parser.parse_args()

    generated = render_openapi_document(generate_openapi_document())
    if args.write:
        OPENAPI_SNAPSHOT.write_text(generated, encoding="utf-8")
        print(f"Updated {OPENAPI_SNAPSHOT.relative_to(PROJECT_ROOT)}")
        return

    if not OPENAPI_SNAPSHOT.exists():
        raise SystemExit(
            "OpenAPI snapshot is missing. Run `python scripts/check_openapi.py --write` and commit the result."
        )

    expected = OPENAPI_SNAPSHOT.read_text(encoding="utf-8")
    if expected == generated:
        print("OpenAPI snapshot is up to date")
        return

    diff = unified_diff(
        expected.splitlines(),
        generated.splitlines(),
        fromfile="docs/openapi.json (committed)",
        tofile="docs/openapi.json (generated)",
        lineterm="",
    )
    sys.stderr.write("\n".join(diff) + "\n")
    raise SystemExit(
        "OpenAPI drift detected. Review the contract change, then run "
        "`python scripts/check_openapi.py --write`."
    )


if __name__ == "__main__":
    main()
