"""Dataset browsing, Agent evaluation and built-in annotation editor endpoints."""

import asyncio
import hashlib
import io
import json
import logging
import mimetypes
import os
import tempfile
import uuid
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Annotated, cast
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from PIL import Image
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user, get_db_session, get_real_dataset_service, require_roles
from src.config import IngestionSettings
from src.models.auth_schemas import AuthenticatedUser
from src.models.inference_schemas import InferenceBatchRequest, InferenceImageReference, InferenceResponse
from src.models.ingestion import QAImage, QAObject
from src.models.real_dataset_schemas import (
    AnnotationDocument,
    AnnotationRestoreRequest,
    AnnotationRevisionList,
    AnnotationSaveRequest,
    RealDatasetBatchEvaluation,
    RealDatasetBatchEvaluationRequest,
    RealDatasetBatchEvaluationResult,
    RealDatasetBBox,
    RealDatasetEvaluation,
    RealDatasetFrameSample,
    RealDatasetFrameSampleList,
    RealDatasetImage,
    RealDatasetImageList,
    RealDatasetLabel,
)
from src.services.annotation_editor_service import AnnotationConflictError, AnnotationEditorService
from src.services.google_cloud import create_gcs_storage_client
from src.services.ingestion.yolo_detection_adapter import YoloDatasetLayoutError
from src.services.real_dataset_qa_service import RealDatasetQaService
from src.services.real_dataset_service import RealDatasetService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _EvaluationImage:
    image_id: str
    image: RealDatasetImage
    image_row: QAImage | None
    revision: int


@dataclass(frozen=True)
class _EvaluationInput:
    image_id: str
    image: RealDatasetImage
    image_payload: bytes | None
    image_reference: InferenceImageReference | None
    revision: int


router = APIRouter(
    prefix="/dataset",
    tags=["Real Dataset QA"],
    dependencies=[Depends(get_current_user)],
)

_CAMERA_ORDER = {
    "CAM_FRONT": 0,
    "CAM_FRONT_RIGHT": 1,
    "CAM_BACK_RIGHT": 2,
    "CAM_BACK": 3,
    "CAM_BACK_LEFT": 4,
    "CAM_FRONT_LEFT": 5,
}
_DATASET_DEFAULT_SPLITS = {
    "kitti": "full",
    "nuscenes": "trainval-full",
}
_FALLBACK_SPLIT = "product"
_DEFAULT_GCS_CACHE_ROOT = (
    Path("/app/data")
    if os.name != "nt" and Path("/app").is_dir()
    else Path(tempfile.gettempdir()) / "label-guardian" / "data"
)
_DATABASE_LIST_TIMEOUT_SECONDS = 20.0
_ORIGINAL_CACHE_MAX_BYTES = 2 * 1024 * 1024 * 1024
_THUMBNAIL_CACHE_MAX_BYTES = 256 * 1024 * 1024
_CACHE_EVICTION_TARGET_RATIO = 0.75
_CACHE_LOCKS = tuple(asyncio.Lock() for _ in range(64))


def _configured_cache_limit(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r; expected a byte count", name, raw_value)
        return default
    if value < 0:
        logger.warning("Ignoring negative %s=%r; expected a byte count", name, raw_value)
        return default
    return value


def _cache_lock(key: str) -> asyncio.Lock:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return _CACHE_LOCKS[int.from_bytes(digest[:2], "big") % len(_CACHE_LOCKS)]


def _cache_file_key(service: RealDatasetService, split: str, image_id: str) -> str:
    identity = "\0".join((service.dataset_id, service.dataset_version, split, image_id))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _touch_cache_file(path: Path) -> None:
    try:
        path.touch(exist_ok=True)
    except OSError:
        pass


def _write_cache_file(path: Path, payload: bytes) -> bool:
    temporary_path = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_bytes(payload)
        os.replace(temporary_path, path)
        return True
    except OSError:
        logger.warning("Could not write dataset cache file %s", path, exc_info=True)
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _evict_cache_directory(directory: Path, maximum_bytes: int) -> None:
    if maximum_bytes <= 0 or not directory.is_dir():
        return
    files: list[tuple[Path, int, float]] = []
    total_bytes = 0
    for path in directory.iterdir():
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        files.append((path, stat.st_size, stat.st_mtime))
        total_bytes += stat.st_size
    if total_bytes <= maximum_bytes:
        return
    target_bytes = int(maximum_bytes * _CACHE_EVICTION_TARGET_RATIO)
    for path, size, _modified_at in sorted(files, key=lambda item: item[2]):
        try:
            path.unlink(missing_ok=True)
            total_bytes -= size
        except OSError:
            continue
        if total_bytes <= target_bytes:
            break


async def _evict_cache_if_needed() -> None:
    original_limit = _configured_cache_limit(
        "LABEL_GUARDIAN_IMAGE_CACHE_MAX_BYTES",
        _ORIGINAL_CACHE_MAX_BYTES,
    )
    thumbnail_limit = _configured_cache_limit(
        "LABEL_GUARDIAN_THUMBNAIL_CACHE_MAX_BYTES",
        _THUMBNAIL_CACHE_MAX_BYTES,
    )

    def evict() -> None:
        cache_root = _gcs_cache_root()
        _evict_cache_directory(cache_root / "original", original_limit)
        _evict_cache_directory(cache_root / "thumbnails", thumbnail_limit)

    await asyncio.to_thread(evict)


def _not_found(error: Exception) -> HTTPException:
    return HTTPException(status_code=404, detail=str(error))


def _cache_storage_path(root: Path, storage_filename: str) -> Path:
    path = root / storage_filename
    if path.is_file() or PurePosixPath(storage_filename).parts[:1] == ("frames",):
        return path
    return root / "frames" / storage_filename


def _split_from_filename(filename: str, default_split: str) -> str:
    parts = filename.split("/")
    if len(parts) >= 3 and parts[0] == "images":
        return parts[1]
    return default_split


def _database_image_split(image: QAImage, default_split: str) -> str:
    identity = _frame_sample_identity(image.storage_key)
    return identity[0] if identity else _split_from_filename(image.filename, default_split)


def _dataset_release(service: RealDatasetService, dataset: str | None) -> tuple[str, str]:
    """Resolve the canonical release served for each supported dataset."""
    selected_dataset = (dataset or service.dataset_id).lower()
    release = (
        "object" if selected_dataset == "kitti" and service.dataset_version != "product" else service.dataset_version
    )
    return selected_dataset, release


def _image_dataset_release(service: RealDatasetService, image: RealDatasetImage) -> tuple[str, str]:
    """Return the dataset identity that owns an image contract."""
    dataset_id = (image.dataset or service.dataset_id).lower()
    dataset_version = image.release or _dataset_release(service, dataset_id)[1]
    return dataset_id, dataset_version


def _database_dataset_conditions(
    service: RealDatasetService,
    dataset: str | None = None,
) -> tuple[object, object]:
    """Scope metadata reads to the selected dataset and its canonical release."""
    selected_dataset, release = _dataset_release(service, dataset)
    return (
        func.lower(QAImage.dataset) == selected_dataset,
        QAImage.release == release,
    )


def _escaped_like_segment(value: str) -> str:
    """Escape a user-provided path segment before using it in a LIKE pattern."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _database_image_split_condition(split: str) -> object:
    escaped_split = _escaped_like_segment(split)
    return or_(
        QAImage.storage_key.like(f"%/{escaped_split}/frames/%", escape="\\"),
        QAImage.filename.like(f"images/{escaped_split}/%", escape="\\"),
    )


def _database_frame_split_condition(split: str) -> object:
    escaped_split = _escaped_like_segment(split)
    return QAImage.storage_key.like(f"%/{escaped_split}/frames/%", escape="\\")


def _content_url(split: str, image_id: str) -> str:
    return f"/api/v1/dataset/images/{split}/{image_id}/content"


def _frame_sample_identity(storage_key: str | None) -> tuple[str, str, str, str] | None:
    """Return split, sequence, sample and camera for a canonical frame object key."""
    if not storage_key:
        return None
    parts = PurePosixPath(storage_key.replace("\\", "/")).parts
    try:
        frames_index = parts.index("frames")
    except ValueError:
        return None
    if frames_index == 0 or len(parts) != frames_index + 4:
        return None
    split, sequence_id, sample_id, camera_file = (
        parts[frames_index - 1],
        parts[frames_index + 1],
        parts[frames_index + 2],
        parts[frames_index + 3],
    )
    camera_channel = PurePosixPath(camera_file).stem
    if not camera_channel:
        return None
    return split, sequence_id, sample_id, camera_channel


def _split_from_storage_key(storage_key: str | None, default_split: str) -> str:
    identity = _frame_sample_identity(storage_key)
    if identity is not None:
        return identity[0]
    return default_split


def _dataset_name(row: QAImage) -> str | None:
    return row.dataset or (
        PurePosixPath(row.storage_key).parts[2]
        if row.storage_key and len(PurePosixPath(row.storage_key).parts) > 2
        else None
    )


def _matches_dataset(row: QAImage, dataset: str | None) -> bool:
    if not dataset:
        return True
    return (_dataset_name(row) or "").lower() == dataset.lower()


def _selected_split(requested_split: str | None, dataset: str | None, service: RealDatasetService) -> str:
    if requested_split:
        return requested_split
    dataset_default = _DATASET_DEFAULT_SPLITS.get((dataset or service.dataset_id).lower())
    if dataset_default:
        return dataset_default
    return cast(str, service.default_split)


def _split_candidates(requested_split: str | None, dataset: str | None, service: RealDatasetService) -> list[str]:
    """Prefer the requested/default full split and fall back to product."""
    selected = _selected_split(requested_split, dataset, service)
    return [selected] if selected == _FALLBACK_SPLIT else [selected, _FALLBACK_SPLIT]


def _gcs_cache_root() -> Path:
    return Path(os.environ.get("LABEL_GUARDIAN_GCS_CACHE_ROOT", str(_DEFAULT_GCS_CACHE_ROOT)))


def _cached_object_path(key: str) -> Path | None:
    normalized_key = key.lstrip("/")
    if ".." in PurePosixPath(normalized_key).parts:
        return None
    path = _gcs_cache_root() / normalized_key
    return path if path.is_file() else None


def _official_cache_roots(service: RealDatasetService, dataset: str | None, split: str) -> list[tuple[str, str, Path]]:
    root = _gcs_cache_root() / "datasets" / "official"
    normalized_dataset = (dataset or service.dataset_id).lower()
    if service.dataset_version == "product" and split == "product" and normalized_dataset in {"kitti", "nuscenes"}:
        return [(normalized_dataset, split, root / normalized_dataset / "product")]
    if normalized_dataset == "kitti":
        if split == _FALLBACK_SPLIT:
            return [("kitti", _FALLBACK_SPLIT, root / "kitti" / "object" / _FALLBACK_SPLIT)]
        return [
            ("kitti", split, root / "kitti" / "object" / split),
            ("kitti", _FALLBACK_SPLIT, root / "kitti" / "object" / _FALLBACK_SPLIT),
        ]
    if normalized_dataset == "nuscenes":
        version = service.dataset_version if service.dataset_id == "nuscenes" else "v1.0-trainval"
        if split == _FALLBACK_SPLIT:
            return [
                ("nuscenes", _FALLBACK_SPLIT, root / "nuscenes" / version / _FALLBACK_SPLIT),
                ("nuscenes", _FALLBACK_SPLIT, root / "nuscenes" / "v1.0-mini" / _FALLBACK_SPLIT),
            ]
        return [
            ("nuscenes", split, root / "nuscenes" / version / split),
            ("nuscenes", _FALLBACK_SPLIT, root / "nuscenes" / version / _FALLBACK_SPLIT),
            ("nuscenes", _FALLBACK_SPLIT, root / "nuscenes" / "v1.0-mini" / _FALLBACK_SPLIT),
        ]
    return [
        ("nuscenes", _FALLBACK_SPLIT, root / "nuscenes" / "v1.0-trainval" / _FALLBACK_SPLIT),
        ("nuscenes", _FALLBACK_SPLIT, root / "nuscenes" / "v1.0-mini" / _FALLBACK_SPLIT),
        ("kitti", _FALLBACK_SPLIT, root / "kitti" / "object" / _FALLBACK_SPLIT),
    ]


@lru_cache(maxsize=32)
def _load_official_cache(root: str) -> tuple[list[dict[str, object]], dict[str, list[dict[str, object]]]]:
    cache_root = Path(root)
    manifest_path = cache_root / "manifests" / "image_manifest.jsonl"
    objects_path = cache_root / "annotations" / "normalized_objects.jsonl"
    images: list[dict[str, object]] = []
    objects_by_image: dict[str, list[dict[str, object]]] = defaultdict(list)
    if manifest_path.is_file():
        with manifest_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    images.append(json.loads(line))
    if objects_path.is_file():
        with objects_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                item = json.loads(line)
                source_image_id = item.get("source_image_id")
                if isinstance(source_image_id, str):
                    objects_by_image[source_image_id].append(item)
    return images, objects_by_image


def _cache_image_contract(
    *,
    dataset: str,
    split: str,
    root: Path,
    image: dict[str, object],
    objects: Sequence[dict[str, object]],
) -> RealDatasetImage | None:
    source_image_id = image.get("source_image_id")
    storage_filename = image.get("storage_filename")
    width = image.get("width")
    height = image.get("height")
    if not isinstance(source_image_id, str) or not isinstance(storage_filename, str):
        return None
    if not isinstance(width, int) or not isinstance(height, int):
        return None
    storage_path = _cache_storage_path(root, storage_filename)
    storage_parts = PurePosixPath(storage_path.relative_to(root).as_posix()).parts
    if len(storage_parts) < 4:
        return None
    sequence_id, sample_id, camera_file = storage_parts[-3], storage_parts[-2], storage_parts[-1]
    labels: list[RealDatasetLabel] = []
    for index, item in enumerate(objects):
        bbox = item.get("bbox")
        label = item.get("label")
        if not isinstance(bbox, dict) or not isinstance(label, str):
            continue
        try:
            labels.append(
                RealDatasetLabel(
                    id=str(index),
                    class_name=label,
                    bbox=RealDatasetBBox(
                        x1=float(bbox["xmin"]),
                        y1=float(bbox["ymin"]),
                        x2=float(bbox["xmax"]),
                        y2=float(bbox["ymax"]),
                    ),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    relative_prefix = root.relative_to(_gcs_cache_root()).as_posix()
    storage_key = f"{relative_prefix}/{storage_path.relative_to(root).as_posix()}"
    return RealDatasetImage(
        id=source_image_id,
        split=split,
        dataset=dataset,
        release="product"
        if root.name == "product" and root.parent.name == dataset
        else root.parent.name
        if dataset == "nuscenes"
        else "object",
        filename=storage_key,
        width=width,
        height=height,
        label_count=len(labels),
        labels=labels,
        image_url=_content_url(split, source_image_id),
        frame_sample_id=sample_id,
        sequence_id=sequence_id,
        camera_channel=PurePosixPath(camera_file).stem,
    )


def _cached_image_contract(service: RealDatasetService, split: str, image_id: str) -> RealDatasetImage | None:
    for cache_dataset, cache_split, root in _official_cache_roots(service, None, split):
        images, objects_by_image = _load_official_cache(str(root))
        for image in images:
            if image.get("source_image_id") != image_id:
                continue
            return _cache_image_contract(
                dataset=cache_dataset,
                split=cache_split,
                root=root,
                image=image,
                objects=objects_by_image.get(image_id, []),
            )
    return None


def _list_official_cache_frame_samples(
    service: RealDatasetService,
    *,
    split: str,
    dataset: str | None,
    limit: int,
    offset: int,
    sequence_id: str | None = None,
) -> RealDatasetFrameSampleList | None:
    for cache_dataset, cache_split, root in _official_cache_roots(service, dataset, split):
        images, objects_by_image = _load_official_cache(str(root))
        if not images:
            continue
        grouped: dict[tuple[str, str], list[RealDatasetImage]] = defaultdict(list)
        classes: set[str] = set()
        for image in images:
            source_image_id = image.get("source_image_id")
            if not isinstance(source_image_id, str):
                continue
            contract = _cache_image_contract(
                dataset=cache_dataset,
                split=cache_split,
                root=root,
                image=image,
                objects=objects_by_image.get(source_image_id, []),
            )
            if contract is None or contract.sequence_id is None or contract.frame_sample_id is None:
                continue
            if sequence_id and contract.sequence_id != sequence_id:
                continue
            grouped[(contract.sequence_id, contract.frame_sample_id)].append(contract)
            classes.update(label.class_name for label in contract.labels)
        ordered_groups = sorted(grouped.items(), key=lambda item: item[0])
        page_groups = ordered_groups[offset : offset + limit]
        results: list[RealDatasetFrameSample] = []
        for (sequence_id, sample_id), cameras in page_groups:
            cameras.sort(
                key=lambda camera: (_CAMERA_ORDER.get(camera.camera_channel or "", 99), camera.camera_channel or "")
            )
            results.append(
                RealDatasetFrameSample(
                    id=f"{sequence_id}/{sample_id}",
                    sample_id=sample_id,
                    sequence_id=sequence_id,
                    split=cache_split,
                    dataset=cache_dataset,
                    camera_count=len(cameras),
                    label_count=sum(camera.label_count for camera in cameras),
                    cameras=cameras,
                )
            )
        return RealDatasetFrameSampleList(
            count=len(ordered_groups),
            image_count=sum(len(cameras) for cameras in grouped.values()),
            results=results,
            split=cache_split,
            dataset=cache_dataset,
            limit=limit,
            offset=offset,
            available_splits=[cache_split, split] if cache_split != split else [cache_split],
            available_datasets=["nuscenes", "kitti"],
            classes=sorted(classes),
        )
    return None


def _cached_image_content(service: RealDatasetService, split: str, image_id: str) -> tuple[Path, str] | None:
    for _cache_dataset, _cache_split, root in _official_cache_roots(service, None, split):
        images, _objects_by_image = _load_official_cache(str(root))
        for image in images:
            if image.get("source_image_id") != image_id:
                continue
            storage_filename = image.get("storage_filename")
            if not isinstance(storage_filename, str):
                continue
            path = _cache_storage_path(root, storage_filename)
            if path.is_file():
                return path, mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return None


def _bucket_and_key(image: QAImage) -> tuple[str, str]:
    settings = IngestionSettings()
    if image.storage_key:
        return settings.bucket_name, image.storage_key.lstrip("/")
    if not image.object_url:
        raise FileNotFoundError(f"Dataset image has no cloud object URL: {image.source_image_id}")
    if image.object_url.startswith("gs://"):
        bucket_and_key = image.object_url.removeprefix("gs://")
        bucket, _, key = bucket_and_key.partition("/")
        if bucket and key:
            return bucket, key
    parsed = urlparse(image.object_url)
    if parsed.netloc == "storage.googleapis.com":
        bucket, _, key = parsed.path.lstrip("/").partition("/")
        if bucket and key:
            return bucket, key
    raise FileNotFoundError(f"Dataset image does not have a supported GCS URL: {image.source_image_id}")


@lru_cache(maxsize=1)
def _get_process_gcs_client():  # type: ignore[no-untyped-def]
    return create_gcs_storage_client(IngestionSettings())


def _gcs_blob(image: QAImage):  # type: ignore[no-untyped-def]
    bucket_name, key = _bucket_and_key(image)
    client = _get_process_gcs_client()
    blob = client.bucket(bucket_name).blob(key)
    return blob


def _download_gcs_image(image: QAImage) -> tuple[bytes, str]:
    blob = _gcs_blob(image)
    try:
        payload = blob.download_as_bytes()
    except Exception as error:
        if getattr(error, "code", None) != 404:
            raise
        raise FileNotFoundError(
            f"Dataset image object does not exist in GCS: gs://{blob.bucket.name}/{blob.name}"
        ) from error
    filename = getattr(image, "storage_key", None) or getattr(image, "filename", None) or ""
    content_type = blob.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return payload, content_type


def _validated_storage_segment(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized or normalized in {".", ".."} or "/" in normalized or "\\" in normalized:
        raise FileNotFoundError(f"Invalid point-cloud {field}: {value}")
    return normalized


def _stream_gcs_pointcloud(
    dataset_id: str,
    dataset_version: str,
    split: str,
    sequence_id: str,
    sample_id: str,
) -> tuple[Iterator[bytes], dict[str, str]]:
    """Stream a point cloud belonging to the API service's configured release."""
    settings = IngestionSettings()
    safe_dataset = _validated_storage_segment(dataset_id, "dataset")
    safe_version = _validated_storage_segment(dataset_version, "release")
    safe_split = _validated_storage_segment(split, "split")
    safe_sequence = _validated_storage_segment(sequence_id, "sequence")
    safe_sample = _validated_storage_segment(sample_id, "sample")
    prefix = f"datasets/official/{safe_dataset}/{safe_version}/{safe_split}/pointclouds/{safe_sequence}/{safe_sample}"
    client = _get_process_gcs_client()
    bucket = client.bucket(settings.bucket_name)
    blob = next(
        (
            candidate
            for key in (f"{prefix}/LIDAR_TOP.pcd.bin", f"{prefix}/LIDAR_TOP.bin")
            if (candidate := bucket.blob(key)).exists(client=client)
        ),
        None,
    )
    if blob is None:
        raise FileNotFoundError(
            f"Dataset point cloud does not exist in {safe_dataset}/{safe_version}/{safe_split}: "
            f"{safe_sequence}/{safe_sample}"
        )
    blob.chunk_size = 1024 * 1024

    def chunks() -> Iterator[bytes]:
        with blob.open("rb") as stream:
            while chunk := stream.read(blob.chunk_size):
                yield chunk

    headers = {"Cache-Control": "private, max-age=31536000, immutable"}
    if blob.etag:
        headers["ETag"] = blob.etag
    return chunks(), headers


async def _db_image_to_contract(
    session: AsyncSession,
    image: QAImage,
    *,
    split: str,
    objects: Sequence[QAObject] | None = None,
) -> RealDatasetImage:
    identity = _frame_sample_identity(image.storage_key)
    if objects is None:
        objects = (
            await session.scalars(select(QAObject).where(QAObject.image_id == image.id).order_by(QAObject.id))
        ).all()
    labels = [
        RealDatasetLabel(
            id=str(item.id),
            class_name=item.label,
            bbox=RealDatasetBBox(x1=item.xmin, y1=item.ymin, x2=item.xmax, y2=item.ymax),
        )
        for item in objects
    ]
    image_contract = RealDatasetImage(
        id=image.source_image_id,
        split=split,
        dataset=_dataset_name(image),
        release=image.release,
        filename=image.storage_key or image.filename,
        width=image.width,
        height=image.height,
        label_count=len(labels),
        labels=labels,
        image_url=_content_url(split, image.source_image_id),
        frame_sample_id=identity[2] if identity else None,
        sequence_id=identity[1] if identity else None,
        camera_channel=identity[3] if identity else None,
    )
    return image_contract


async def _apply_latest_revisions(
    session: AsyncSession,
    service: RealDatasetService,
    images: list[RealDatasetImage],
    *,
    split: str,
    dataset: str | None = None,
) -> list[RealDatasetImage]:
    dataset_id, dataset_version = _dataset_release(service, dataset)
    revisions = await AnnotationEditorService.latest_for_images(
        session,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        split=split,
        image_ids=[image.id for image in images],
    )
    return [
        AnnotationEditorService.to_document(
            image,
            dataset_id,
            dataset_version,
            revisions.get(image.id),
        ).image
        for image in images
    ]


async def _list_database_frame_samples(
    session: AsyncSession,
    service: RealDatasetService,
    *,
    split: str | None,
    dataset: str | None,
    limit: int,
    offset: int,
    sequence_id: str | None = None,
) -> RealDatasetFrameSampleList:
    selected_split = split or service.default_split
    base_conditions = list(_database_dataset_conditions(service, dataset))
    frame_conditions = [*base_conditions, _database_frame_split_condition(selected_split)]
    if sequence_id:
        escaped_sequence_id = _escaped_like_segment(sequence_id)
        frame_conditions.append(QAImage.storage_key.like(f"%/frames/{escaped_sequence_id}/%", escape="\\"))
    frame_group_key = func.regexp_replace(QAImage.storage_key, r"/[^/]+$", "")
    group_keys = (
        await session.scalars(
            select(frame_group_key)
            .where(*frame_conditions)
            .group_by(frame_group_key)
            .order_by(frame_group_key)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    rows = (
        (
            await session.scalars(
                select(QAImage)
                .where(*frame_conditions, frame_group_key.in_(group_keys))
                .order_by(QAImage.storage_key, QAImage.id)
            )
        ).all()
        if group_keys
        else []
    )
    grouped: dict[tuple[str, str], list[tuple[QAImage, str]]] = {}
    for row in rows:
        identity = _frame_sample_identity(row.storage_key)
        if identity is None:
            continue
        row_split, sequence_id, sample_id, camera_channel = identity
        if row_split == selected_split:
            grouped.setdefault((sequence_id, sample_id), []).append((row, camera_channel))

    ordered_groups = sorted(grouped.items(), key=lambda item: item[0])
    page_groups = ordered_groups
    page_image_ids = [row.id for _, camera_rows in page_groups for row, _ in camera_rows]
    object_rows = (
        (
            await session.scalars(
                select(QAObject).where(QAObject.image_id.in_(page_image_ids)).order_by(QAObject.image_id, QAObject.id)
            )
        ).all()
        if page_image_ids
        else []
    )
    objects_by_image: dict[int, list[QAObject]] = defaultdict(list)
    for object_row in object_rows:
        objects_by_image[object_row.image_id].append(object_row)
    ordered_cameras: list[tuple[tuple[str, str], list[tuple[QAImage, str]]]] = []
    for (sequence_id, sample_id), camera_rows in page_groups:
        camera_rows.sort(key=lambda item: (_CAMERA_ORDER.get(item[1], 99), item[1]))
        ordered_cameras.append(((sequence_id, sample_id), camera_rows))

    flat_cameras = [
        await _db_image_to_contract(
            session,
            row,
            split=selected_split,
            objects=objects_by_image[row.id],
        )
        for _, camera_rows in ordered_cameras
        for row, _ in camera_rows
    ]
    flat_cameras = await _apply_latest_revisions(
        session,
        service,
        flat_cameras,
        split=selected_split,
        dataset=dataset,
    )

    results: list[RealDatasetFrameSample] = []
    camera_index = 0
    for (sequence_id, sample_id), camera_rows in ordered_cameras:
        camera_count = len(camera_rows)
        cameras = flat_cameras[camera_index : camera_index + camera_count]
        camera_index += camera_count
        results.append(
            RealDatasetFrameSample(
                id=f"{sequence_id}/{sample_id}",
                sample_id=sample_id,
                sequence_id=sequence_id,
                split=selected_split,
                dataset=dataset,
                camera_count=len(cameras),
                label_count=sum(camera.label_count for camera in cameras),
                cameras=cameras,
            )
        )

    class_rows = (
        await session.scalars(
            select(QAObject.label)
            .join(QAImage, QAImage.id == QAObject.image_id)
            .where(*frame_conditions)
            .distinct()
            .order_by(QAObject.label)
        )
    ).all()
    group_count = int(
        await session.scalar(select(func.count(func.distinct(frame_group_key))).where(*frame_conditions)) or 0
    )
    image_count = int(await session.scalar(select(func.count()).select_from(QAImage).where(*frame_conditions)) or 0)
    return RealDatasetFrameSampleList(
        count=group_count,
        image_count=image_count,
        results=results,
        split=selected_split,
        dataset=dataset,
        limit=limit,
        offset=offset,
        available_splits=[selected_split],
        available_datasets=[(dataset or service.dataset_id).lower()],
        classes=list(class_rows),
    )


async def _list_database_frame_sequences(
    session: AsyncSession,
    service: RealDatasetService,
    *,
    split: str,
    dataset: str | None,
) -> list[str]:
    conditions = [
        *_database_dataset_conditions(service, dataset),
        _database_frame_split_condition(split),
    ]
    # Some ingestions include a split segment before /frames and some use the
    # release itself as the split, so extract relative to the stable marker.
    sequence_key = func.regexp_replace(QAImage.storage_key, r"^.*/frames/([^/]+)/.*$", r"\1")
    return list(
        (
            await session.scalars(
                select(sequence_key)
                .where(*conditions, QAImage.storage_key.is_not(None), sequence_key != "")
                .distinct()
                .order_by(sequence_key)
            )
        ).all()
    )


async def _list_filesystem_frame_samples(
    session: AsyncSession,
    service: RealDatasetService,
    *,
    split: str | None,
    limit: int,
    offset: int,
) -> RealDatasetFrameSampleList:
    image_list = service.list_images(split=split, limit=limit, offset=offset)
    images = await _apply_latest_revisions(
        session,
        service,
        image_list.results,
        split=image_list.split,
    )
    samples = [
        RealDatasetFrameSample(
            id=image.id,
            sample_id=image.id,
            sequence_id=image.split,
            split=image.split,
            camera_count=1,
            label_count=image.label_count,
            cameras=[image],
        )
        for image in images
    ]
    return RealDatasetFrameSampleList(
        count=image_list.count,
        image_count=image_list.count,
        results=samples,
        split=image_list.split,
        dataset=None,
        limit=image_list.limit,
        offset=image_list.offset,
        available_splits=image_list.available_splits,
        available_datasets=[],
        classes=image_list.classes,
    )


async def _list_database_images(
    session: AsyncSession,
    service: RealDatasetService,
    *,
    split: str | None,
    dataset: str | None,
    limit: int,
    offset: int,
) -> RealDatasetImageList:
    selected_split = split or service.default_split
    base_conditions = list(_database_dataset_conditions(service, dataset))
    split_conditions = [*base_conditions, _database_image_split_condition(selected_split)]
    rows = (
        await session.scalars(
            select(QAImage).where(*split_conditions).order_by(QAImage.filename, QAImage.id).limit(limit).offset(offset)
        )
    ).all()
    class_rows = (
        await session.scalars(
            select(QAObject.label)
            .join(QAImage, QAImage.id == QAObject.image_id)
            .where(*split_conditions)
            .distinct()
            .order_by(QAObject.label)
        )
    ).all()
    image_count = int(await session.scalar(select(func.count()).select_from(QAImage).where(*split_conditions)) or 0)
    image_ids = [row.id for row in rows]
    object_rows = (
        (
            await session.scalars(
                select(QAObject).where(QAObject.image_id.in_(image_ids)).order_by(QAObject.image_id, QAObject.id)
            )
        ).all()
        if image_ids
        else []
    )
    objects_by_image: dict[int, list[QAObject]] = defaultdict(list)
    for object_row in object_rows:
        objects_by_image[object_row.image_id].append(object_row)
    images = [
        await _db_image_to_contract(
            session,
            row,
            split=selected_split,
            objects=objects_by_image[row.id],
        )
        for row in rows
    ]
    images = await _apply_latest_revisions(
        session,
        service,
        images,
        split=selected_split,
        dataset=dataset,
    )
    return RealDatasetImageList(
        count=image_count,
        results=images,
        split=selected_split,
        dataset=dataset,
        limit=limit,
        offset=offset,
        available_splits=[selected_split],
        available_datasets=[(dataset or service.dataset_id).lower()],
        classes=list(class_rows),
    )


async def _get_database_image(
    session: AsyncSession,
    service: RealDatasetService,
    image_id: str,
    *,
    split: str,
) -> RealDatasetImage:
    image = await _get_database_image_row(session, service, image_id, split=split)
    base_image = await _db_image_to_contract(session, image, split=split)
    dataset_id, dataset_version = _image_dataset_release(service, base_image)
    return (
        await AnnotationEditorService.document(
            session,
            image=base_image,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
        )
    ).image


async def _get_database_image_row(
    session: AsyncSession,
    service: RealDatasetService,
    image_id: str,
    *,
    split: str,
) -> QAImage:
    supported_release = or_(
        and_(func.lower(QAImage.dataset) == "nuscenes", QAImage.release == service.dataset_version),
        and_(func.lower(QAImage.dataset) == "kitti", QAImage.release == _dataset_release(service, "kitti")[1]),
    )
    image = await session.scalar(
        select(QAImage).where(
            QAImage.source_image_id == image_id,
            supported_release,
        )
    )
    if image is None or _database_image_split(image, service.default_split) != split:
        raise FileNotFoundError(f"Dataset image does not exist in a supported release for split {split}: {image_id}")
    return cast(QAImage, image)


@router.get("/images", response_model=RealDatasetImageList)
async def list_real_dataset_images(
    service: Annotated[RealDatasetService, Depends(get_real_dataset_service)],
    split: str | None = Query(default=None),
    dataset: str | None = Query(default=None),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> RealDatasetImageList:
    try:
        if service.dataset_backend == "database":
            return await _list_database_images(
                session,
                service,
                split=split,
                dataset=dataset,
                limit=limit,
                offset=offset,
            )
        result = service.list_images(split=split, limit=limit, offset=offset)
        result.results = await _apply_latest_revisions(
            session,
            service,
            result.results,
            split=result.split,
        )
        return result
    except (FileNotFoundError, YoloDatasetLayoutError) as error:
        raise _not_found(error) from error


@router.get("/frame-samples", response_model=RealDatasetFrameSampleList)
async def list_real_dataset_frame_samples(
    service: Annotated[RealDatasetService, Depends(get_real_dataset_service)],
    split: str | None = Query(default=None),
    dataset: str | None = Query(default=None),
    sequence_id: str | None = Query(default=None),
    limit: int = Query(default=8, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> RealDatasetFrameSampleList:
    """List canonical frame samples, grouping all camera views into one review item."""
    try:
        if service.dataset_backend == "database":
            candidates = _split_candidates(split, dataset, service)
            empty_result: RealDatasetFrameSampleList | None = None
            last_error: Exception | None = None
            for selected_split in candidates:
                try:
                    result = await asyncio.wait_for(
                        _list_database_frame_samples(
                            session,
                            service,
                            split=selected_split,
                            dataset=dataset,
                            limit=limit,
                            offset=offset,
                            sequence_id=sequence_id,
                        ),
                        timeout=_DATABASE_LIST_TIMEOUT_SECONDS,
                    )
                    if result.count > 0:
                        return result
                    empty_result = result
                except TimeoutError as error:
                    last_error = error
                    await session.rollback()
                    logger.warning(
                        "frame-samples DB query timed out for split=%s dataset=%s",
                        selected_split,
                        dataset,
                    )
                except Exception as error:
                    last_error = error
                    await session.rollback()
                    logger.exception(
                        "frame-samples DB query failed for split=%s dataset=%s",
                        selected_split,
                        dataset,
                    )
                cached = _list_official_cache_frame_samples(
                    service,
                    split=selected_split,
                    dataset=dataset,
                    limit=limit,
                    offset=offset,
                    sequence_id=sequence_id,
                )
                if cached is not None:
                    return cached
            if empty_result is not None:
                return empty_result
            if isinstance(last_error, TimeoutError):
                raise HTTPException(status_code=504, detail="Dataset frame query timed out.") from last_error
            if last_error is not None:
                raise last_error
            raise HTTPException(status_code=503, detail="Dataset frames are temporarily unavailable.")
        return await _list_filesystem_frame_samples(session, service, split=split, limit=limit, offset=offset)
    except (FileNotFoundError, YoloDatasetLayoutError) as error:
        raise _not_found(error) from error


@router.get("/frame-sequences", response_model=list[str])
async def list_real_dataset_frame_sequences(
    service: Annotated[RealDatasetService, Depends(get_real_dataset_service)],
    split: str | None = Query(default=None),
    dataset: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> list[str]:
    selected_split = _selected_split(split, dataset, service)
    if service.dataset_backend != "database":
        return [selected_split]
    try:
        return await asyncio.wait_for(
            _list_database_frame_sequences(
                session,
                service,
                split=selected_split,
                dataset=dataset,
            ),
            timeout=_DATABASE_LIST_TIMEOUT_SECONDS,
        )
    except TimeoutError as error:
        await session.rollback()
        logger.warning(
            "frame-sequences DB query timed out for split=%s dataset=%s",
            selected_split,
            dataset,
        )
        raise HTTPException(status_code=504, detail="Dataset sequence query timed out.") from error


@router.get("/images/{split}/{image_id}", response_model=RealDatasetImage)
async def get_real_dataset_image(
    split: str,
    image_id: str,
    service: Annotated[RealDatasetService, Depends(get_real_dataset_service)],
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: AsyncSession = Depends(get_db_session),
) -> RealDatasetImage:
    try:
        if service.dataset_backend == "database":
            try:
                return await _get_database_image(session, service, image_id, split=split)
            except FileNotFoundError:
                cached = _cached_image_contract(service, split, image_id)
                if cached is not None:
                    return cached
                raise
        base_image = service.get_image(split, image_id)
        return (
            await AnnotationEditorService.document(
                session,
                image=base_image,
                dataset_id=service.dataset_id,
                dataset_version=service.dataset_version,
            )
        ).image
    except (FileNotFoundError, YoloDatasetLayoutError) as error:
        raise _not_found(error) from error


def _generate_thumbnail(image_bytes: bytes) -> bytes:
    with Image.open(io.BytesIO(image_bytes)) as image:
        image.thumbnail((240, 135), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="WebP", quality=80, method=4)
        return output.getvalue()


async def _thumbnail_from_file(path: Path) -> bytes:
    def generate() -> bytes:
        with Image.open(path) as image:
            image.thumbnail((240, 135), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="WebP", quality=80, method=4)
            return output.getvalue()

    return await asyncio.to_thread(generate)


def _immutable_private_cache_headers() -> dict[str, str]:
    return {"Cache-Control": "private, max-age=31536000, immutable"}


@router.get("/images/{split}/{image_id}/content", response_class=Response, response_model=None)
async def get_real_dataset_image_content(
    split: str,
    image_id: str,
    service: Annotated[RealDatasetService, Depends(get_real_dataset_service)],
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
    size: str | None = Query(default=None),
) -> FileResponse | StreamingResponse | Response:
    if size not in {None, "thumbnail"}:
        raise HTTPException(status_code=400, detail="Invalid size parameter.")

    try:
        cache_key = _cache_file_key(service, split, image_id)
        thumbnail_path = _gcs_cache_root() / "thumbnails" / f"{cache_key}.webp"
        if size == "thumbnail" and thumbnail_path.is_file():
            _touch_cache_file(thumbnail_path)
            return FileResponse(
                thumbnail_path,
                media_type="image/webp",
                headers=_immutable_private_cache_headers(),
            )

        if service.dataset_backend == "database":
            cached = _cached_image_content(service, split, image_id)
            if cached is not None:
                path, media_type = cached
                if size != "thumbnail":
                    return FileResponse(
                        path,
                        media_type=media_type,
                        headers=_immutable_private_cache_headers(),
                    )
                async with _cache_lock(f"thumbnail:{cache_key}"):
                    if thumbnail_path.is_file():
                        _touch_cache_file(thumbnail_path)
                    else:
                        thumbnail_bytes = await _thumbnail_from_file(path)
                        if not _write_cache_file(thumbnail_path, thumbnail_bytes):
                            return Response(
                                content=thumbnail_bytes,
                                media_type="image/webp",
                                headers=_immutable_private_cache_headers(),
                            )
                        background_tasks.add_task(_evict_cache_if_needed)
                return FileResponse(
                    thumbnail_path,
                    media_type="image/webp",
                    headers=_immutable_private_cache_headers(),
                )

            image = await _get_database_image_row(session, service, image_id, split=split)
            if size == "thumbnail":
                async with _cache_lock(f"thumbnail:{cache_key}"):
                    if thumbnail_path.is_file():
                        _touch_cache_file(thumbnail_path)
                    else:
                        image_bytes, _content_type = await asyncio.to_thread(_download_gcs_image, image)
                        thumbnail_bytes = await asyncio.to_thread(_generate_thumbnail, image_bytes)
                        if not _write_cache_file(thumbnail_path, thumbnail_bytes):
                            return Response(
                                content=thumbnail_bytes,
                                media_type="image/webp",
                                headers=_immutable_private_cache_headers(),
                            )
                        background_tasks.add_task(_evict_cache_if_needed)
                return FileResponse(
                    thumbnail_path,
                    media_type="image/webp",
                    headers=_immutable_private_cache_headers(),
                )

            suffix = Path(image.filename).suffix.lower() or ".img"
            original_path = _gcs_cache_root() / "original" / f"{cache_key}{suffix}"
            content_type = mimetypes.guess_type(image.filename)[0] or "application/octet-stream"
            async with _cache_lock(f"original:{cache_key}"):
                if original_path.is_file():
                    _touch_cache_file(original_path)
                    return FileResponse(
                        original_path,
                        media_type=content_type,
                        headers=_immutable_private_cache_headers(),
                    )
                image_bytes, downloaded_content_type = await asyncio.to_thread(_download_gcs_image, image)
                content_type = downloaded_content_type or content_type
                if _write_cache_file(original_path, image_bytes):
                    background_tasks.add_task(_evict_cache_if_needed)
            return Response(
                content=image_bytes,
                media_type=content_type,
                headers=_immutable_private_cache_headers(),
            )

        path = service.image_path(split, image_id)
        if size == "thumbnail":
            async with _cache_lock(f"thumbnail:{cache_key}"):
                if thumbnail_path.is_file():
                    _touch_cache_file(thumbnail_path)
                else:
                    thumbnail_bytes = await _thumbnail_from_file(path)
                    if not _write_cache_file(thumbnail_path, thumbnail_bytes):
                        return Response(
                            content=thumbnail_bytes,
                            media_type="image/webp",
                            headers=_immutable_private_cache_headers(),
                        )
                    background_tasks.add_task(_evict_cache_if_needed)
            return FileResponse(
                thumbnail_path,
                media_type="image/webp",
                headers=_immutable_private_cache_headers(),
            )
    except (FileNotFoundError, YoloDatasetLayoutError) as error:
        raise _not_found(error) from error
    return FileResponse(path, headers=_immutable_private_cache_headers())


@router.get(
    "/pointclouds/{dataset_path:path}/{split}/{sequence_id}/{sample_id}/content",
    response_class=Response,
    response_model=None,
)
async def get_real_dataset_pointcloud_content(
    dataset_path: str,
    split: str,
    sequence_id: str,
    sample_id: str,
    service: Annotated[RealDatasetService, Depends(get_real_dataset_service)],
) -> StreamingResponse:
    try:
        configured_path = f"{service.dataset_id}/{service.dataset_version}"
        if dataset_path.strip("/") != configured_path:
            raise FileNotFoundError(f"Dataset release is not served by this API: {dataset_path}")
        if service.dataset_backend != "database":
            raise FileNotFoundError("Local filesystem backend does not support point clouds.")
        chunks, headers = await asyncio.to_thread(
            _stream_gcs_pointcloud,
            service.dataset_id,
            service.dataset_version,
            split,
            sequence_id,
            sample_id,
        )
        return StreamingResponse(
            chunks,
            media_type="application/octet-stream",
            headers=headers,
        )
    except (FileNotFoundError, YoloDatasetLayoutError) as error:
        raise _not_found(error) from error


async def _prepare_evaluation_input(
    session: AsyncSession,
    service: RealDatasetService,
    split: str,
    image_id: str,
) -> _EvaluationInput:
    prepared = await _prepare_evaluation_image(session, service, split, image_id)
    image_payload: bytes | None = None
    image_reference: InferenceImageReference | None = None
    if service.dataset_backend == "database":
        if prepared.image_row is None:
            raise FileNotFoundError(f"Dataset image does not exist in database for split {split}: {image_id}")
        if service.uses_remote_inference:
            bucket, object_key = _bucket_and_key(prepared.image_row)
            dataset_id, dataset_version = _image_dataset_release(service, prepared.image)
            image_reference = InferenceImageReference(
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                split=split,
                image_id=image_id,
                bucket=bucket,
                object_key=object_key,
            )
        else:
            image_payload, _ = await asyncio.to_thread(_download_gcs_image, prepared.image_row)

    return _EvaluationInput(
        image_id=image_id,
        image=prepared.image,
        image_payload=image_payload,
        image_reference=image_reference,
        revision=prepared.revision,
    )


async def _prepare_evaluation_image(
    session: AsyncSession,
    service: RealDatasetService,
    split: str,
    image_id: str,
) -> _EvaluationImage:
    image_row: QAImage | None = None
    if service.dataset_backend == "database":
        image_row = await _get_database_image_row(session, service, image_id, split=split)
        base_image = await _db_image_to_contract(session, image_row, split=split)
        dataset_id, dataset_version = _image_dataset_release(service, base_image)
    else:
        base_image = service.get_image(split, image_id)
        dataset_id = service.dataset_id
        dataset_version = service.dataset_version
    effective_image = (
        await AnnotationEditorService.document(
            session,
            image=base_image,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
        )
    ).image
    dataset_id, dataset_version = _image_dataset_release(service, effective_image)
    latest = await AnnotationEditorService.latest_revision(
        session,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        split=split,
        image_id=image_id,
    )
    return _EvaluationImage(
        image_id=image_id,
        image=effective_image,
        image_row=image_row,
        revision=latest.version if latest else 0,
    )


@router.post("/images/{split}/{image_id}/evaluate", response_model=RealDatasetEvaluation)
async def evaluate_real_dataset_image(
    split: str,
    image_id: str,
    service: Annotated[RealDatasetService, Depends(get_real_dataset_service)],
    _operator: Annotated[AuthenticatedUser, Depends(require_roles("reviewer", "admin"))],
    force: bool = Query(default=False),
    persist: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
) -> RealDatasetEvaluation:
    try:
        prepared = await _prepare_evaluation_input(session, service, split, image_id)
        evaluation = await service.evaluate(
            split,
            image_id,
            force=force,
            image_override=prepared.image,
            image_payload=prepared.image_payload,
            image_reference=prepared.image_reference,
            revision=prepared.revision,
        )
        if not persist:
            return evaluation
        case_ids = await RealDatasetQaService().persist(session, evaluation)
        evaluation.persisted = True
        evaluation.created_case_ids = case_ids
        return evaluation
    except (FileNotFoundError, YoloDatasetLayoutError) as error:
        raise _not_found(error) from error


@router.get("/images/{split}/{image_id}/evaluation", response_model=RealDatasetEvaluation)
async def get_real_dataset_image_evaluation(
    split: str,
    image_id: str,
    service: Annotated[RealDatasetService, Depends(get_real_dataset_service)],
    _operator: Annotated[AuthenticatedUser, Depends(require_roles("reviewer", "admin"))],
    session: AsyncSession = Depends(get_db_session),
) -> RealDatasetEvaluation:
    try:
        prepared = await _prepare_evaluation_image(session, service, split, image_id)
        dataset_id, dataset_version = _image_dataset_release(service, prepared.image)
        evaluation = await RealDatasetQaService().latest_evaluation(
            session,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            split=split,
            image_id=image_id,
            image=prepared.image,
            revision=prepared.revision,
        )
        if evaluation is None:
            raise HTTPException(status_code=404, detail="No persisted evaluation for image")
        return evaluation
    except (FileNotFoundError, YoloDatasetLayoutError) as error:
        raise _not_found(error) from error


@router.post("/images/{split}/evaluate-batch", response_model=RealDatasetBatchEvaluation)
async def evaluate_real_dataset_images_batch(
    split: str,
    request: RealDatasetBatchEvaluationRequest,
    service: Annotated[RealDatasetService, Depends(get_real_dataset_service)],
    _operator: Annotated[AuthenticatedUser, Depends(require_roles("reviewer", "admin"))],
    session: AsyncSession = Depends(get_db_session),
) -> RealDatasetBatchEvaluation:
    qa_service = RealDatasetQaService()
    prepared_inputs: list[_EvaluationInput] = []
    results: list[RealDatasetBatchEvaluationResult] = []
    for image_id in request.image_ids:
        try:
            prepared_inputs.append(await _prepare_evaluation_input(session, service, split, image_id))
        except HTTPException as error:
            results.append(RealDatasetBatchEvaluationResult(image_id=image_id, error=str(error.detail)))
        except (FileNotFoundError, YoloDatasetLayoutError) as error:
            results.append(RealDatasetBatchEvaluationResult(image_id=image_id, error=str(error)))

    inference_responses: dict[str, InferenceResponse] = {}
    inference_errors: dict[str, str] = {}
    inference_batch_used = False
    batch_client = (
        service.inference_client
        if service.inference_client is not None and hasattr(service.inference_client, "detect_batch")
        else None
    )
    remote_inputs = [item for item in prepared_inputs if item.image_reference is not None]
    if batch_client is not None and len(remote_inputs) == len(prepared_inputs):
        batch_size = 64
        for start in range(0, len(remote_inputs), batch_size):
            chunk = remote_inputs[start : start + batch_size]
            try:
                batch_response = await batch_client.detect_batch(
                    InferenceBatchRequest(
                        images=[item.image_reference for item in chunk if item.image_reference is not None]
                    )
                )
            except Exception as error:
                for item in chunk:
                    inference_errors[item.image_id] = f"Batch inference failed: {error}"
                continue
            inference_batch_used = True
            for item in batch_response.results:
                if item.error:
                    inference_errors[item.image.image_id] = item.error
                    continue
                inference_responses[item.image.image_id] = InferenceResponse(
                    model_name=batch_response.model_name,
                    model_version=batch_response.model_version,
                    detections=item.detections,
                    raw_risk_score=item.raw_risk_score,
                    latency_ms=item.latency_ms,
                    metadata={
                        **item.metadata,
                        "batch_latency_ms": batch_response.latency_ms,
                        "batch_metadata": batch_response.metadata,
                    },
                )

    if inference_batch_used:
        for item in remote_inputs:
            if item.image_id not in inference_responses and item.image_id not in inference_errors:
                inference_errors[item.image_id] = "Inference batch omitted this image."

    for item in prepared_inputs:
        if item.image_id in inference_errors:
            results.append(
                RealDatasetBatchEvaluationResult(
                    image_id=item.image_id,
                    error=inference_errors[item.image_id],
                )
            )
            continue
        try:
            evaluation = await service.evaluate(
                split,
                item.image_id,
                force=request.force,
                image_override=item.image,
                image_payload=item.image_payload,
                image_reference=item.image_reference,
                inference_response=inference_responses.get(item.image_id),
                revision=item.revision,
            )
            if evaluation.report.status == "error":
                results.append(
                    RealDatasetBatchEvaluationResult(image_id=item.image_id, error=evaluation.report.summary)
                )
                continue
            if request.persist:
                case_ids = await qa_service.persist(session, evaluation)
                evaluation.persisted = True
                evaluation.created_case_ids = case_ids
            results.append(
                RealDatasetBatchEvaluationResult(
                    image_id=item.image_id,
                    evaluation=evaluation,
                )
            )
        except Exception:
            await session.rollback()
            logger.exception("Batch QA evaluation failed for image %s", item.image_id)
            results.append(
                RealDatasetBatchEvaluationResult(
                    image_id=item.image_id,
                    error="QA evaluation failed for this image.",
                )
            )

    order = {image_id: index for index, image_id in enumerate(request.image_ids)}
    results.sort(key=lambda result: order[result.image_id])
    succeeded = sum(1 for result in results if result.evaluation is not None)
    failed = len(results) - succeeded
    return RealDatasetBatchEvaluation(
        count=len(results),
        succeeded=succeeded,
        failed=failed,
        inference_batch_used=inference_batch_used,
        results=results,
    )


async def _base_editor_image(
    session: AsyncSession,
    service: RealDatasetService,
    *,
    split: str,
    image_id: str,
) -> RealDatasetImage:
    if service.dataset_backend == "database":
        try:
            image = await _get_database_image_row(session, service, image_id, split=split)
            return await _db_image_to_contract(session, image, split=split)
        except FileNotFoundError:
            cached = _cached_image_contract(service, split, image_id)
            if cached is not None:
                return cached
            raise
    return service.get_image(split, image_id)


@router.get("/images/{split}/{image_id}/annotations", response_model=AnnotationDocument)
async def get_image_annotations(
    split: str,
    image_id: str,
    service: Annotated[RealDatasetService, Depends(get_real_dataset_service)],
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: AsyncSession = Depends(get_db_session),
) -> AnnotationDocument:
    try:
        image = await _base_editor_image(session, service, split=split, image_id=image_id)
        dataset_id, dataset_version = _image_dataset_release(service, image)
        return await AnnotationEditorService.document(
            session,
            image=image,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
        )
    except (FileNotFoundError, YoloDatasetLayoutError) as error:
        raise _not_found(error) from error


@router.put("/images/{split}/{image_id}/annotations", response_model=AnnotationDocument)
async def save_image_annotations(
    split: str,
    image_id: str,
    request: AnnotationSaveRequest,
    service: Annotated[RealDatasetService, Depends(get_real_dataset_service)],
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_roles("annotator", "reviewer", "admin")),
    ],
    session: AsyncSession = Depends(get_db_session),
) -> AnnotationDocument:
    try:
        image = await _base_editor_image(session, service, split=split, image_id=image_id)
        dataset_id, dataset_version = _image_dataset_release(service, image)
        return await AnnotationEditorService.save(
            session,
            image=image,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            expected_revision=request.expected_revision,
            labels=request.labels,
            actor_id=current_user.id,
            change_note=request.change_note,
        )
    except AnnotationConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (FileNotFoundError, YoloDatasetLayoutError) as error:
        raise _not_found(error) from error


@router.get("/images/{split}/{image_id}/annotations/history", response_model=AnnotationRevisionList)
async def get_image_annotation_history(
    split: str,
    image_id: str,
    service: Annotated[RealDatasetService, Depends(get_real_dataset_service)],
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: AsyncSession = Depends(get_db_session),
) -> AnnotationRevisionList:
    image = await _base_editor_image(session, service, split=split, image_id=image_id)
    dataset_id, dataset_version = _image_dataset_release(service, image)
    return await AnnotationEditorService.history(
        session,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        split=split,
        image_id=image_id,
    )


@router.post("/images/{split}/{image_id}/annotations/restore", response_model=AnnotationDocument)
async def restore_image_annotations(
    split: str,
    image_id: str,
    request: AnnotationRestoreRequest,
    service: Annotated[RealDatasetService, Depends(get_real_dataset_service)],
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_roles("annotator", "reviewer", "admin")),
    ],
    session: AsyncSession = Depends(get_db_session),
) -> AnnotationDocument:
    try:
        image = await _base_editor_image(session, service, split=split, image_id=image_id)
        dataset_id, dataset_version = _image_dataset_release(service, image)
        return await AnnotationEditorService.restore(
            session,
            image=image,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            expected_revision=request.expected_revision,
            target_revision=request.target_revision,
            actor_id=current_user.id,
            change_note=request.change_note,
        )
    except AnnotationConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (FileNotFoundError, YoloDatasetLayoutError) as error:
        raise _not_found(error) from error
