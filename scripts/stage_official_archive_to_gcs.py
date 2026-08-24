#!/usr/bin/env python3
"""Stream an official dataset archive directly into Google Cloud Storage."""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import IngestionSettings  # noqa: E402
from src.services.ingestion.official_dataset_downloader import NUSCENES_MINI_URL, _format_bytes  # noqa: E402


def _parse_gs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError("Destination must be a gs:// URI.")
    bucket_and_key = uri.removeprefix("gs://")
    bucket, _, key = bucket_and_key.partition("/")
    if not bucket or not key:
        raise ValueError("Destination must include both bucket and object key.")
    return bucket, key


def _content_type_for_url(url: str) -> str:
    name = Path(url.split("?", 1)[0]).name.lower()
    if name.endswith((".tgz", ".tar.gz")):
        return "application/gzip"
    if name.endswith(".zip"):
        return "application/zip"
    return "application/octet-stream"


def stage_archive(url: str, destination: str, *, project: str | None = None, chunk_size: int = 8 * 1024 * 1024) -> None:
    try:
        from google.cloud import storage  # type: ignore[import-untyped]
    except ImportError as error:
        raise RuntimeError("Google Cloud Storage support requires `pip install -e '.[ingestion]'`.") from error

    settings = IngestionSettings()
    bucket_name, object_key = _parse_gs_uri(destination)
    client = storage.Client(project=project or settings.gcs_project)
    blob = client.bucket(bucket_name).blob(object_key)
    blob.chunk_size = chunk_size

    request = urllib.request.Request(url)
    with urllib.request.urlopen(request, timeout=60) as response:
        total = int(response.headers.get("Content-Length") or 0)
        content_type = response.headers.get("Content-Type") or _content_type_for_url(url)
        print(f"[stage] Streaming {url} -> {destination} ({content_type})", flush=True)
        copied = 0
        with blob.open("wb", content_type=content_type) as output:
            while chunk := response.read(chunk_size):
                output.write(chunk)
                copied += len(chunk)
                if total:
                    print(
                        f"[stage] {_format_bytes(copied)} / {_format_bytes(total)} ({copied / total * 100:.1f}%)",
                        flush=True,
                    )
                else:
                    print(f"[stage] {_format_bytes(copied)}", flush=True)
    print(f"[stage] Complete: {destination}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage official dataset archives directly to GCS without local cache.")
    parser.add_argument("--url", default=NUSCENES_MINI_URL)
    parser.add_argument(
        "--destination",
        default="gs://label_guardian_bucket/raw/official/nuscenes/v1.0-mini/archives/v1.0-mini.tgz",
    )
    parser.add_argument("--gcp-project")
    parser.add_argument("--chunk-size-mib", type=int, default=8)
    args = parser.parse_args()
    stage_archive(
        args.url,
        args.destination,
        project=args.gcp_project,
        chunk_size=args.chunk_size_mib * 1024 * 1024,
    )


if __name__ == "__main__":
    main()
