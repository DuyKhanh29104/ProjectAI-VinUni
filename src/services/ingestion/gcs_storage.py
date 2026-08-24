"""Google Cloud Storage adapter with the boto3 upload subset used by ingestion."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, cast

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from src.config import IngestionSettings
from src.services.google_cloud import create_gcs_storage_client


class GCSBlobRangeReader(io.RawIOBase):
    """Seekable reader that serves ZIP range reads without full object download."""

    def __init__(self, blob: Any, size: int) -> None:
        self.blob = blob
        self.size = size
        self.position = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            next_position = offset
        elif whence == io.SEEK_CUR:
            next_position = self.position + offset
        elif whence == io.SEEK_END:
            next_position = self.size + offset
        else:
            raise ValueError(f"Unsupported seek mode: {whence}")
        if next_position < 0:
            raise ValueError("Negative seek position")
        self.position = min(next_position, self.size)
        return self.position

    def read(self, size: int = -1) -> bytes:
        if self.position >= self.size:
            return b""
        if size is None or size < 0:
            end = self.size - 1
        else:
            end = min(self.position + size, self.size) - 1
        if end < self.position:
            return b""
        payload = cast(bytes, self.blob.download_as_bytes(start=self.position, end=end))
        self.position += len(payload)
        return payload


class GCSObjectStorageClient:
    """Small boto3-compatible subset backed by Google Cloud Storage."""

    def __init__(self, settings: IngestionSettings) -> None:
        try:
            from google.api_core.exceptions import NotFound  # type: ignore[import-untyped]
        except ImportError as error:
            raise RuntimeError(
                "Google Cloud Storage support requires `pip install -e '.[ingestion]'`."
            ) from error

        self.not_found_error = NotFound
        self.client = create_gcs_storage_client(settings)

    def head_bucket(self, **kwargs: Any) -> None:
        bucket_name = kwargs["Bucket"]
        try:
            self.client.get_bucket(bucket_name)
        except self.not_found_error as error:
            raise ClientError({"Error": {"Code": "404"}}, "HeadBucket") from error

    def create_bucket(self, **kwargs: Any) -> None:
        bucket_name = kwargs["Bucket"]
        self.client.create_bucket(bucket_name)

    def upload_file(self, filename: str, bucket: str, key: str, **kwargs: Any) -> None:
        content_type = (kwargs.get("ExtraArgs") or {}).get("ContentType")
        blob = self.client.bucket(bucket).blob(key)
        blob.upload_from_filename(str(Path(filename)), content_type=content_type)

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        destination = Path(filename)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.client.bucket(bucket).blob(key).download_to_filename(str(destination))

    def open_reader(self, bucket: str, key: str) -> GCSBlobRangeReader:
        blob = self.client.bucket(bucket).blob(key)
        blob.reload()
        size = int(blob.size or 0)
        return GCSBlobRangeReader(blob, size)

    def object_exists(self, bucket: str, key: str) -> bool:
        return bool(self.client.bucket(bucket).blob(key).exists())

    def copy_object(self, bucket: str, source_key: str, destination_key: str) -> None:
        bucket_obj = self.client.bucket(bucket)
        source = bucket_obj.blob(source_key)
        bucket_obj.copy_blob(source, bucket_obj, destination_key)

    def list_objects(self, bucket: str, prefix: str) -> list[str]:
        return [blob.name for blob in self.client.bucket(bucket).list_blobs(prefix=prefix)]

    def object_size(self, bucket: str, key: str) -> int | None:
        blob = self.client.bucket(bucket).blob(key)
        if not blob.exists():
            return None
        blob.reload()
        return cast(int | None, blob.size)


def create_gcs_client(settings: IngestionSettings) -> GCSObjectStorageClient:
    """Create a GCS storage client for the ingestion worker."""
    return GCSObjectStorageClient(settings)
