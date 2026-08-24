"""Dataset browsing, Agent evaluation and built-in annotation editor endpoints."""

import asyncio
from collections import defaultdict
from collections.abc import Iterator, Sequence
from pathlib import PurePosixPath
from typing import Annotated, cast
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user, get_db_session, get_real_dataset_service, require_roles
from src.config import IngestionSettings
from src.models.auth_schemas import AuthenticatedUser
from src.models.ingestion import QAImage, QAObject
from src.models.real_dataset_schemas import (
    AnnotationDocument,
    AnnotationRestoreRequest,
    AnnotationRevisionList,
    AnnotationSaveRequest,
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


def _not_found(error: Exception) -> HTTPException:
    return HTTPException(status_code=404, detail=str(error))


def _split_from_filename(filename: str, default_split: str) -> str:
    parts = filename.split("/")
    if len(parts) >= 3 and parts[0] == "images":
        return parts[1]
    return default_split


def _database_image_split(image: QAImage, default_split: str) -> str:
    identity = _frame_sample_identity(image.storage_key)
    return identity[0] if identity else _split_from_filename(image.filename, default_split)


def _database_dataset_conditions(service: RealDatasetService) -> tuple[object, object]:
    """Scope every metadata read to the configured dataset and release."""
    return (
        QAImage.dataset == service.dataset_id,
        QAImage.release == service.dataset_version,
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


def _database_metadata_split(storage_key: str | None, filename: str, default_split: str) -> str:
    identity = _frame_sample_identity(storage_key)
    return identity[0] if identity else _split_from_filename(filename, default_split)


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
    return row.dataset or (PurePosixPath(row.storage_key).parts[2] if row.storage_key and len(PurePosixPath(row.storage_key).parts) > 2 else None)


def _matches_dataset(row: QAImage, dataset: str | None) -> bool:
    if not dataset:
        return True
    return (_dataset_name(row) or "").lower() == dataset.lower()


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


def _gcs_blob(image: QAImage):  # type: ignore[no-untyped-def]
    settings = IngestionSettings()
    bucket_name, key = _bucket_and_key(image)
    client = create_gcs_storage_client(settings)
    blob = client.bucket(bucket_name).blob(key)
    if not blob.exists(client=client):
        raise FileNotFoundError(f"Dataset image object does not exist in GCS: gs://{bucket_name}/{key}")
    blob.reload(client=client)
    return blob


def _download_gcs_image(image: QAImage) -> tuple[bytes, str]:
    blob = _gcs_blob(image)
    return blob.download_as_bytes(), blob.content_type or "application/octet-stream"


def _stream_gcs_image(image: QAImage) -> tuple[Iterator[bytes], str, dict[str, str]]:
    """Stream a private GCS object without buffering the full frame in RAM."""
    blob = _gcs_blob(image)
    blob.chunk_size = 1024 * 1024

    def chunks() -> Iterator[bytes]:
        with blob.open("rb") as stream:
            while chunk := stream.read(blob.chunk_size):
                yield chunk

    headers = {"Cache-Control": "private, max-age=300"}
    if blob.etag:
        headers["ETag"] = blob.etag
    return chunks(), blob.content_type or "application/octet-stream", headers


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
    prefix = (
        f"datasets/official/{safe_dataset}/{safe_version}/{safe_split}/"
        f"pointclouds/{safe_sequence}/{safe_sample}"
    )
    client = create_gcs_storage_client(settings)
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

    headers = {"Cache-Control": "private, max-age=300"}
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
) -> list[RealDatasetImage]:
    revisions = await AnnotationEditorService.latest_for_images(
        session,
        dataset_id=service.dataset_id,
        dataset_version=service.dataset_version,
        split=split,
        image_ids=[image.id for image in images],
    )
    return [
        AnnotationEditorService.to_document(
            image,
            service.dataset_id,
            service.dataset_version,
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
) -> RealDatasetFrameSampleList:
    selected_split = split or service.default_split
    base_conditions = list(_database_dataset_conditions(service))
    if dataset:
        base_conditions.append(func.lower(QAImage.dataset) == dataset.lower())
    frame_conditions = [*base_conditions, _database_frame_split_condition(selected_split)]
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
    metadata_rows = (
        await session.execute(
            select(QAImage.storage_key, QAImage.filename, QAImage.dataset).where(
                *_database_dataset_conditions(service)
            )
        )
    ).all()
    grouped: dict[tuple[str, str], list[tuple[QAImage, str]]] = {}
    available_splits = {
        _database_metadata_split(storage_key, filename, service.default_split)
        for storage_key, filename, _ in metadata_rows
    }
    available_datasets = sorted({name for _, _, name in metadata_rows if name})
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
    results: list[RealDatasetFrameSample] = []
    for (sequence_id, sample_id), camera_rows in page_groups:
        camera_rows.sort(key=lambda item: (_CAMERA_ORDER.get(item[1], 99), item[1]))
        cameras = [
            await _db_image_to_contract(
                session,
                row,
                split=selected_split,
                objects=objects_by_image[row.id],
            )
            for row, _ in camera_rows
        ]
        cameras = await _apply_latest_revisions(
            session,
            service,
            cameras,
            split=selected_split,
        )
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
        available_splits=sorted(available_splits) or [selected_split],
        available_datasets=available_datasets,
        classes=list(class_rows),
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
    base_conditions = list(_database_dataset_conditions(service))
    if dataset:
        base_conditions.append(func.lower(QAImage.dataset) == dataset.lower())
    split_conditions = [*base_conditions, _database_image_split_condition(selected_split)]
    metadata_rows = (
        await session.execute(
            select(QAImage.storage_key, QAImage.filename, QAImage.dataset).where(
                *_database_dataset_conditions(service)
            )
        )
    ).all()
    available_splits = sorted(
        {
            _database_metadata_split(storage_key, filename, service.default_split)
            for storage_key, filename, _ in metadata_rows
        }
    ) or [selected_split]
    rows = (
        await session.scalars(
            select(QAImage)
            .where(*split_conditions)
            .order_by(QAImage.filename, QAImage.id)
            .limit(limit)
            .offset(offset)
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
    images = [await _db_image_to_contract(session, row, split=selected_split) for row in rows]
    images = await _apply_latest_revisions(session, service, images, split=selected_split)
    return RealDatasetImageList(
        count=image_count,
        results=images,
        split=selected_split,
        dataset=dataset,
        limit=limit,
        offset=offset,
        available_splits=available_splits,
        available_datasets=sorted({name for _, _, name in metadata_rows if name}),
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
    return (
        await AnnotationEditorService.document(
            session,
            image=base_image,
            dataset_id=service.dataset_id,
            dataset_version=service.dataset_version,
        )
    ).image


async def _get_database_image_row(
    session: AsyncSession,
    service: RealDatasetService,
    image_id: str,
    *,
    split: str,
) -> QAImage:
    image = await session.scalar(
        select(QAImage).where(
            QAImage.source_image_id == image_id,
            *_database_dataset_conditions(service),
        )
    )
    if image is None or _database_image_split(image, service.default_split) != split:
        raise FileNotFoundError(
            f"Dataset image does not exist in {service.dataset_id}/{service.dataset_version}/{split}: {image_id}"
        )
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
    limit: int = Query(default=8, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> RealDatasetFrameSampleList:
    """List canonical frame samples, grouping all camera views into one review item."""
    try:
        if service.dataset_backend == "database":
            return await _list_database_frame_samples(
                session,
                service,
                split=split,
                dataset=dataset,
                limit=limit,
                offset=offset,
            )
        return await _list_filesystem_frame_samples(session, service, split=split, limit=limit, offset=offset)
    except (FileNotFoundError, YoloDatasetLayoutError) as error:
        raise _not_found(error) from error


@router.get("/images/{split}/{image_id}", response_model=RealDatasetImage)
async def get_real_dataset_image(
    split: str,
    image_id: str,
    service: Annotated[RealDatasetService, Depends(get_real_dataset_service)],
    session: AsyncSession = Depends(get_db_session),
) -> RealDatasetImage:
    try:
        if service.dataset_backend == "database":
            return await _get_database_image(session, service, image_id, split=split)
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


@router.get("/images/{split}/{image_id}/content", response_class=Response, response_model=None)
async def get_real_dataset_image_content(
    split: str,
    image_id: str,
    service: Annotated[RealDatasetService, Depends(get_real_dataset_service)],
    session: AsyncSession = Depends(get_db_session),
) -> FileResponse | StreamingResponse:
    try:
        if service.dataset_backend == "database":
            image = await _get_database_image_row(session, service, image_id, split=split)
            chunks, content_type, headers = await asyncio.to_thread(_stream_gcs_image, image)
            return StreamingResponse(
                chunks,
                media_type=content_type,
                headers=headers,
            )
        path = service.image_path(split, image_id)
    except (FileNotFoundError, YoloDatasetLayoutError) as error:
        raise _not_found(error) from error
    return FileResponse(path)


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
            raise FileNotFoundError(
                f"Dataset release is not served by this API: {dataset_path}"
            )
        if service.dataset_backend != "database":
            raise FileNotFoundError(
                "Local filesystem backend does not support point clouds."
            )
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
        image_payload: bytes | None = None
        if service.dataset_backend == "database":
            image_row = await _get_database_image_row(session, service, image_id, split=split)
            effective_image = await _get_database_image(session, service, image_id, split=split)
            image_payload, _ = await asyncio.to_thread(_download_gcs_image, image_row)
        else:
            base_image = service.get_image(split, image_id)
            effective_image = (
                await AnnotationEditorService.document(
                    session,
                    image=base_image,
                    dataset_id=service.dataset_id,
                    dataset_version=service.dataset_version,
                )
            ).image
        latest = await AnnotationEditorService.latest_revision(
            session,
            dataset_id=service.dataset_id,
            dataset_version=service.dataset_version,
            split=split,
            image_id=image_id,
        )
        evaluation = await service.evaluate(
            split,
            image_id,
            force=force,
            image_override=effective_image,
            image_payload=image_payload,
            revision=latest.version if latest else 0,
        )
        if not persist:
            return evaluation
        case_ids = await RealDatasetQaService().persist(session, evaluation)
        evaluation.persisted = True
        evaluation.created_case_ids = case_ids
        return evaluation
    except (FileNotFoundError, YoloDatasetLayoutError) as error:
        raise _not_found(error) from error


async def _base_editor_image(
    session: AsyncSession,
    service: RealDatasetService,
    *,
    split: str,
    image_id: str,
) -> RealDatasetImage:
    if service.dataset_backend == "database":
        image = await _get_database_image_row(session, service, image_id, split=split)
        return await _db_image_to_contract(session, image, split=split)
    return service.get_image(split, image_id)


@router.get("/images/{split}/{image_id}/annotations", response_model=AnnotationDocument)
async def get_image_annotations(
    split: str,
    image_id: str,
    service: Annotated[RealDatasetService, Depends(get_real_dataset_service)],
    session: AsyncSession = Depends(get_db_session),
) -> AnnotationDocument:
    try:
        image = await _base_editor_image(session, service, split=split, image_id=image_id)
        return await AnnotationEditorService.document(
            session,
            image=image,
            dataset_id=service.dataset_id,
            dataset_version=service.dataset_version,
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
        return await AnnotationEditorService.save(
            session,
            image=image,
            dataset_id=service.dataset_id,
            dataset_version=service.dataset_version,
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
    session: AsyncSession = Depends(get_db_session),
) -> AnnotationRevisionList:
    await _base_editor_image(session, service, split=split, image_id=image_id)
    return await AnnotationEditorService.history(
        session,
        dataset_id=service.dataset_id,
        dataset_version=service.dataset_version,
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
        return await AnnotationEditorService.restore(
            session,
            image=image,
            dataset_id=service.dataset_id,
            dataset_version=service.dataset_version,
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
