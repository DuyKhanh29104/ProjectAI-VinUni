"""Filesystem-backed object client for deterministic local ingestion runs."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, BinaryIO


class LocalObjectStorageClient:
    """Small boto3-compatible subset that stores objects beneath a local root."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def head_bucket(self, **kwargs: Any) -> None:
        if not (self.root / kwargs["Bucket"]).is_dir():
            from botocore.exceptions import ClientError  # type: ignore[import-untyped]

            raise ClientError({"Error": {"Code": "404"}}, "HeadBucket")

    def create_bucket(self, **kwargs: Any) -> None:
        (self.root / kwargs["Bucket"]).mkdir(parents=True, exist_ok=True)

    def upload_file(self, filename: str, bucket: str, key: str, **kwargs: Any) -> None:
        del kwargs
        destination = self.root / bucket / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(filename, destination)

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        source = self.root / bucket / key
        destination = Path(filename)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    def open_reader(self, bucket: str, key: str) -> BinaryIO:
        return (self.root / bucket / key).open("rb")

    def object_exists(self, bucket: str, key: str) -> bool:
        return (self.root / bucket / key).is_file()

    def copy_object(self, bucket: str, source_key: str, destination_key: str) -> None:
        source = self.root / bucket / source_key
        destination = self.root / bucket / destination_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    def list_objects(self, bucket: str, prefix: str) -> list[str]:
        bucket_root = self.root / bucket
        if not bucket_root.is_dir():
            return []
        return sorted(
            key
            for key in (path.relative_to(bucket_root).as_posix() for path in bucket_root.rglob("*") if path.is_file())
            if key.startswith(prefix)
        )

    def object_size(self, bucket: str, key: str) -> int | None:
        path = self.root / bucket / key
        return path.stat().st_size if path.is_file() else None
