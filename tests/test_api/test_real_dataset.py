import os
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from PIL import Image

from src.api.real_dataset import (
    _evict_cache_directory,
    _frame_sample_identity,
    _generate_thumbnail,
    _image_dataset_release,
    _official_cache_roots,
    _split_candidates,
    list_real_dataset_frame_samples,
)
from src.config import Settings
from src.main import create_app
from src.models.inference_schemas import (
    InferenceDetection,
    InferenceImageReference,
    InferenceRequest,
    InferenceResponse,
)
from src.models.ingestion import QAImage, QAObject, QAReviewStatus
from src.models.real_dataset_schemas import RealDatasetBBox, RealDatasetImage
from src.services.real_dataset_service import RealDatasetService


class FakeAgent:
    def __init__(self) -> None:
        self.calls = 0
        self.last_state: dict[str, Any] | None = None

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        self.last_state = state
        ground_truth = state["gt_labels"][0]
        return {
            "pred_labels": [{"class_name": "truck", "bbox": ground_truth["bbox"], "confidence": 0.9}],
            "matches": [
                {
                    "gt_id": ground_truth["label_id"],
                    "gt_class": ground_truth["class_name"],
                    "pred_index": 0,
                    "pred_class": "truck",
                    "pred_confidence": 0.9,
                    "iou": 1.0,
                    "class_match": False,
                }
            ],
            "unmatched_gt": [],
            "unmatched_pred": [],
            "qa_report": {
                "image_path": state["image_path"],
                "status": "needs_review",
                "summary": "One deterministic issue.",
                "metrics": {},
                "issues": [
                    {
                        "label_id": ground_truth["label_id"],
                        "issue_type": "wrong_class",
                        "severity": "high",
                        "explanation": "Prediction differs.",
                        "suggested_fix": "Review class.",
                        "evidence": {},
                    }
                ],
            },
        }


class CloudImageAgent(FakeAgent):
    def __init__(self) -> None:
        super().__init__()
        self.image_path: Path | None = None
        self.image_payload: bytes | None = None

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        self.image_path = Path(state["image_path"])
        self.image_payload = self.image_path.read_bytes()
        return await super().ainvoke(state)


@pytest.mark.parametrize(
    ("storage_key", "expected"),
    [
        (
            "datasets/official/nuscenes/v1.0-mini/smoke/frames/scene-0061/"
            "ca9a282c9e77460f8360f564131a8af5/CAM_FRONT.jpg",
            ("smoke", "scene-0061", "ca9a282c9e77460f8360f564131a8af5", "CAM_FRONT"),
        ),
        (
            "datasets/official/nuscenes/v1.0-mini/smoke/frames/scene-0061/sample-1532402927647951/CAM_BACK.jpg",
            ("smoke", "scene-0061", "sample-1532402927647951", "CAM_BACK"),
        ),
    ],
)
def test_frame_sample_identity_accepts_canonical_frame_ids(storage_key, expected):
    assert _frame_sample_identity(storage_key) == expected


@pytest.mark.parametrize(
    ("dataset", "expected_full"),
    [("kitti", "full"), ("nuscenes", "trainval-full")],
)
def test_cloud_dataset_split_candidates_prefer_full_then_product(tmp_path, dataset, expected_full):
    service = RealDatasetService(
        tmp_path,
        dataset_backend="database",
        dataset_id="nuscenes",
        dataset_version="v1.0-trainval",
        default_split="trainval-full",
    )

    assert _split_candidates(None, dataset, service) == [expected_full, "product"]
    assert _split_candidates("product", dataset, service) == ["product"]


def test_kitti_cache_roots_prefer_full_then_product(tmp_path, monkeypatch):
    monkeypatch.setenv("LABEL_GUARDIAN_GCS_CACHE_ROOT", str(tmp_path))
    service = RealDatasetService(tmp_path, dataset_backend="database")

    roots = _official_cache_roots(service, "kitti", "full")

    assert [(dataset, split) for dataset, split, _root in roots] == [
        ("kitti", "full"),
        ("kitti", "product"),
    ]


def test_image_dataset_release_prefers_image_identity(tmp_path):
    service = RealDatasetService(
        tmp_path,
        dataset_backend="database",
        dataset_id="nuscenes",
        dataset_version="v1.0-trainval",
    )
    image = RealDatasetImage.model_validate(
        {
            "id": "000001",
            "split": "full",
            "dataset": "KITTI",
            "release": "object",
            "filename": "000001.png",
            "width": 100,
            "height": 80,
            "labelCount": 0,
            "labels": [],
            "imageUrl": "/api/v1/dataset/images/full/000001/content",
        }
    )

    assert _image_dataset_release(service, image) == ("kitti", "object")


def test_thumbnail_generation_bounds_dimensions_and_uses_webp():
    source = BytesIO()
    Image.new("RGB", (1600, 900), (20, 30, 40)).save(source, format="JPEG")

    thumbnail = _generate_thumbnail(source.getvalue())

    with Image.open(BytesIO(thumbnail)) as image:
        assert image.format == "WEBP"
        assert image.size == (240, 135)


def test_cache_eviction_removes_oldest_files_until_below_target(tmp_path):
    cache_dir = tmp_path / "original"
    cache_dir.mkdir()
    for index in range(4):
        path = cache_dir / f"{index}.jpg"
        path.write_bytes(b"x" * 100)
        path.touch()
        path.chmod(0o600)
        # Keep deterministic oldest-first ordering on filesystems with coarse mtimes.
        os.utime(path, (index + 1, index + 1))

    _evict_cache_directory(cache_dir, 300)

    assert sum(path.stat().st_size for path in cache_dir.iterdir()) <= 225
    assert {path.name for path in cache_dir.iterdir()} == {"2.jpg", "3.jpg"}


@pytest.mark.asyncio
async def test_frame_sample_timeout_rolls_back_and_returns_gateway_timeout(tmp_path, monkeypatch):
    async def time_out(*_args, **_kwargs):
        raise TimeoutError

    session = AsyncMock()
    service = RealDatasetService(
        tmp_path,
        dataset_backend="database",
        dataset_id="nuscenes",
        dataset_version="product",
        default_split="product",
    )
    monkeypatch.setattr("src.api.real_dataset._list_database_frame_samples", time_out)
    monkeypatch.setattr("src.api.real_dataset._list_official_cache_frame_samples", lambda *_args, **_kwargs: None)

    with pytest.raises(HTTPException) as raised:
        await list_real_dataset_frame_samples(
            service,
            split="product",
            dataset="nuscenes",
            sequence_id=None,
            limit=20,
            offset=0,
            session=session,
        )

    assert raised.value.status_code == 504
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_database_pointcloud_is_scoped_to_configured_release(
    tmp_path,
    postgres_async_session_factory,
    postgres_test_database,
    monkeypatch,
):
    calls: list[tuple[str, str, str, str, str]] = []

    def fake_stream(dataset_id, dataset_version, split, sequence_id, sample_id):
        calls.append((dataset_id, dataset_version, split, sequence_id, sample_id))
        return iter([b"fake-pointcloud"]), {"Cache-Control": "private, max-age=300"}

    monkeypatch.setattr("src.api.real_dataset._stream_gcs_pointcloud", fake_stream)
    service = RealDatasetService(
        tmp_path,
        dataset_backend="database",
        dataset_id="nuscenes",
        dataset_version="v1.0-mini",
    )
    application = create_app(
        settings=Settings(
            app_env="test",
            auth_enabled=False,
            database_url=postgres_test_database.async_url,
            _env_file=None,
        ),
        db_session_factory=postgres_async_session_factory,
        real_dataset_service=service,
    )

    async with application.router.lifespan_context(application):
        async with AsyncClient(
            transport=ASGITransport(app=application),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/v1/dataset/pointclouds/nuscenes/v1.0-mini/smoke/scene-0061/sample-1/content"
            )
            foreign = await client.get(
                "/api/v1/dataset/pointclouds/nuscenes/v1.0-trainval/smoke/scene-0061/sample-1/content"
            )

    assert response.status_code == 200
    assert response.content == b"fake-pointcloud"
    assert foreign.status_code == 404
    assert calls == [("nuscenes", "v1.0-mini", "smoke", "scene-0061", "sample-1")]


@pytest.mark.asyncio
async def test_database_evaluation_uses_ephemeral_cloud_image(tmp_path):
    cloud_agent = CloudImageAgent()
    service = RealDatasetService(tmp_path, dataset_backend="database", agent_runner=cloud_agent)
    image = {
        "id": "cloud-image",
        "split": "smoke",
        "filename": "samples/CAM_FRONT/frame.jpg",
        "width": 100,
        "height": 80,
        "labelCount": 1,
        "labels": [
            {
                "id": "label-1",
                "className": "car",
                "bbox": {"x1": 10, "y1": 10, "x2": 30, "y2": 30},
                "attributes": {},
            }
        ],
        "imageUrl": "/api/v1/dataset/images/smoke/cloud-image/content",
    }
    evaluation = await service.evaluate(
        "smoke",
        "cloud-image",
        image_override=RealDatasetImage.model_validate(image),
        image_payload=b"cloud-image-bytes",
    )

    assert cloud_agent.image_payload == b"cloud-image-bytes"
    assert cloud_agent.image_path is not None and not cloud_agent.image_path.exists()
    assert evaluation.report.image_path == image["imageUrl"]


@pytest.mark.asyncio
async def test_evaluation_scopes_identity_to_annotation_revision_and_supported_taxonomy(tmp_path):
    cloud_agent = CloudImageAgent()
    service = RealDatasetService(
        tmp_path,
        dataset_backend="database",
        dataset_id="nuscenes",
        dataset_version="v1.0-trainval",
        agent_runner=cloud_agent,
    )
    image = RealDatasetImage.model_validate(
        {
            "id": "cloud-image",
            "split": "smoke",
            "dataset": "kitti",
            "release": "object",
            "filename": "frame.jpg",
            "width": 100,
            "height": 80,
            "labelCount": 2,
            "labels": [
                {
                    "id": "car-label",
                    "className": "vehicle.car",
                    "bbox": {"x1": 10, "y1": 10, "x2": 30, "y2": 30},
                },
                {
                    "id": "barrier-label",
                    "className": "movable_object.barrier",
                    "bbox": {"x1": 40, "y1": 10, "x2": 60, "y2": 30},
                },
            ],
            "imageUrl": "/api/v1/dataset/images/smoke/cloud-image/content",
        }
    )

    revision_zero = await service.evaluate(
        "smoke", "cloud-image", image_override=image, image_payload=b"image", revision=0
    )
    revision_one = await service.evaluate(
        "smoke", "cloud-image", image_override=image, image_payload=b"image", revision=1
    )

    assert revision_zero.evaluation_id != revision_one.evaluation_id
    assert revision_one.dataset_id == "kitti"
    assert revision_one.dataset_version == "object"
    assert cloud_agent.last_state is not None
    assert cloud_agent.last_state["gt_labels"] == [
        {
            "label_id": "car-label",
            "class_name": "car",
            "bbox": {"x1": 10.0, "y1": 10.0, "x2": 30.0, "y2": 30.0},
        }
    ]
    assert cloud_agent.last_state["metadata"]["unsupported_ground_truth_count"] == 1


@pytest.mark.asyncio
async def test_database_browse_is_scoped_to_configured_dataset_release_and_split(
    tmp_path,
    postgres_async_session_factory,
    postgres_test_database,
):
    async with postgres_async_session_factory() as session:
        session.add_all(
            [
                QAImage(
                    source_image_id="wanted-image",
                    filename="images/smoke/wanted.jpg",
                    width=100,
                    height=80,
                    dataset="nuscenes",
                    release="v1.0-mini",
                    storage_key="datasets/official/nuscenes/v1.0-mini/smoke/frames/scene-1/sample-1/CAM_FRONT.jpg",
                ),
                QAImage(
                    source_image_id="wrong-release",
                    filename="images/smoke/wrong-release.jpg",
                    width=100,
                    height=80,
                    dataset="nuscenes",
                    release="v1.0-trainval",
                    storage_key="datasets/official/nuscenes/v1.0-trainval/smoke/frames/scene-2/sample-2/CAM_FRONT.jpg",
                ),
                QAImage(
                    source_image_id="wrong-split",
                    filename="images/train/wrong-split.jpg",
                    width=100,
                    height=80,
                    dataset="nuscenes",
                    release="v1.0-mini",
                    storage_key="datasets/official/nuscenes/v1.0-mini/train/frames/scene-3/sample-3/CAM_FRONT.jpg",
                ),
            ]
        )
        await session.commit()

    service = RealDatasetService(
        tmp_path,
        dataset_backend="database",
        default_split="smoke",
        dataset_id="nuscenes",
        dataset_version="v1.0-mini",
    )
    application = create_app(
        settings=Settings(
            app_env="test",
            auth_enabled=False,
            database_url=postgres_test_database.async_url,
            _env_file=None,
        ),
        db_session_factory=postgres_async_session_factory,
        real_dataset_service=service,
    )
    async with application.router.lifespan_context(application):
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            listed = await client.get("/api/v1/dataset/images?split=smoke")
            samples = await client.get("/api/v1/dataset/frame-samples?split=smoke")
            sequences = await client.get("/api/v1/dataset/frame-sequences?split=smoke")
            foreign = await client.get("/api/v1/dataset/images/smoke/wrong-release")
            wrong_split = await client.get("/api/v1/dataset/images/smoke/wrong-split")

    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()["results"]] == ["wanted-image"]
    assert [camera["id"] for row in samples.json()["results"] for camera in row["cameras"]] == ["wanted-image"]
    assert sequences.json() == ["scene-1"]
    assert foreign.status_code == 404
    assert wrong_split.status_code == 404


def _write_dataset(root: Path) -> None:
    (root / "images" / "val").mkdir(parents=True)
    (root / "labels" / "val").mkdir(parents=True)
    (root / "class.txt.txt").write_text("car\ntruck\n", encoding="utf-8")
    Image.new("RGB", (100, 80), (20, 30, 40)).save(root / "images" / "val" / "000001.png")
    (root / "labels" / "val" / "000001.txt").write_text("0 0.5 0.5 0.2 0.25\n", encoding="utf-8")


def _app(tmp_path, session_factory, database_url, agent=None):
    return create_app(
        settings=Settings(app_env="test", database_url=database_url.async_url, _env_file=None),
        db_session_factory=session_factory,
        real_dataset_service=RealDatasetService(tmp_path, agent_runner=agent or FakeAgent()),
    )


@pytest.mark.asyncio
async def test_dataset_browse_content_and_agent_evaluation(
    tmp_path,
    postgres_async_session_factory,
    postgres_test_database,
    monkeypatch,
):
    _write_dataset(tmp_path)
    monkeypatch.setenv("LABEL_GUARDIAN_GCS_CACHE_ROOT", str(tmp_path / "cache"))
    agent = FakeAgent()
    application = _app(tmp_path, postgres_async_session_factory, postgres_test_database, agent)
    async with application.router.lifespan_context(application):
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            listed = await client.get("/api/v1/dataset/images?split=val")
            content = await client.get("/api/v1/dataset/images/val/000001/content")
            thumbnail = await client.get("/api/v1/dataset/images/val/000001/content?size=thumbnail")
            evaluated = await client.post("/api/v1/dataset/images/val/000001/evaluate")
            cached = await client.post("/api/v1/dataset/images/val/000001/evaluate")
    assert listed.status_code == 200
    assert listed.json()["results"][0]["labels"][0]["bbox"] == {"x1": 40.0, "y1": 30.0, "x2": 60.0, "y2": 50.0}
    assert content.status_code == 200
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"] == "image/webp"
    with Image.open(BytesIO(thumbnail.content)) as image:
        assert image.size == (100, 80)
    assert evaluated.json()["report"]["issues"][0]["issueType"] == "wrong_class"
    assert cached.json()["cached"] is True
    assert agent.calls == 1


@pytest.mark.asyncio
async def test_evaluation_persists_idempotent_qa_cases(
    tmp_path, postgres_async_session_factory, postgres_test_database
):
    _write_dataset(tmp_path)
    application = _app(tmp_path, postgres_async_session_factory, postgres_test_database)
    async with application.router.lifespan_context(application):
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            first = await client.post("/api/v1/dataset/images/val/000001/evaluate?persist=true")
            second = await client.post("/api/v1/dataset/images/val/000001/evaluate?persist=true")
            cases = await client.get("/api/v1/qa-cases")
    assert first.status_code == 200
    assert second.json()["createdCaseIds"] == first.json()["createdCaseIds"]
    assert cases.json()["results"][0]["sourceImageId"] == "000001"


@pytest.mark.asyncio
async def test_editor_save_conflict_history_and_restore(
    tmp_path, postgres_async_session_factory, postgres_test_database
):
    _write_dataset(tmp_path)
    application = _app(tmp_path, postgres_async_session_factory, postgres_test_database)
    path = "/api/v1/dataset/images/val/000001/annotations"
    changed = [
        {
            "id": "label-1",
            "className": "truck",
            "trackId": "track-7",
            "bbox": {"x1": 35, "y1": 25, "x2": 65, "y2": 55},
            "attributes": {"occluded": True},
        }
    ]
    async with application.router.lifespan_context(application):
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            original = await client.get(path)
            saved = await client.put(
                path,
                json={
                    "expectedRevision": 0,
                    "labels": changed,
                    "actorId": "reviewer-1",
                    "changeNote": "Fix class and box",
                },
            )
            stale = await client.put(path, json={"expectedRevision": 0, "labels": changed})
            listed = await client.get("/api/v1/dataset/images?split=val")
            history = await client.get(f"{path}/history")
            restored = await client.post(
                f"{path}/restore", json={"expectedRevision": 1, "targetRevision": 0, "actorId": "reviewer-1"}
            )
    assert original.json()["revision"] == 0
    assert saved.status_code == 200 and saved.json()["revision"] == 1
    assert saved.json()["labels"] == [{**label, "normalizedClassName": "truck"} for label in changed]
    assert stale.status_code == 409
    assert listed.json()["results"][0]["labels"] == saved.json()["labels"]
    assert history.json()["results"][0]["changeNote"] == "Fix class and box"
    assert restored.json()["revision"] == 2
    assert restored.json()["labels"][0]["className"] == "car"


@pytest.mark.asyncio
async def test_dataset_rejects_path_traversal(client):
    response = await client.get("/api/v1/dataset/images/val/..%2F.env/content")
    assert response.status_code == 404


class FakeInferenceClient:
    def __init__(self) -> None:
        self.requests: list[InferenceRequest] = []

    async def detect(self, request: InferenceRequest) -> InferenceResponse:
        self.requests.append(request)
        return InferenceResponse(
            model_name="remote-yolo",
            model_version="remote-yolo@2026-08-27",
            detections=[
                InferenceDetection(
                    class_name="car",
                    bbox=RealDatasetBBox(x1=10, y1=10, x2=30, y2=30),
                    confidence=0.88,
                )
            ],
            latency_ms={"inference": 12.5},
        )


@pytest.mark.asyncio
async def test_remote_inference_uses_gcs_reference_and_injected_predictions(tmp_path):
    agent = FakeAgent()
    inference_client = FakeInferenceClient()
    service = RealDatasetService(
        tmp_path,
        dataset_backend="database",
        dataset_id="nuscenes",
        dataset_version="v1.0-mini",
        agent_runner=agent,
        inference_client=inference_client,
    )
    image = RealDatasetImage.model_validate(
        {
            "id": "cloud-image",
            "split": "smoke",
            "dataset": "nuscenes",
            "release": "v1.0-mini",
            "filename": "frame.jpg",
            "width": 100,
            "height": 80,
            "labelCount": 1,
            "labels": [
                {
                    "id": "car-label",
                    "className": "vehicle.car",
                    "bbox": {"x1": 10, "y1": 10, "x2": 30, "y2": 30},
                }
            ],
            "imageUrl": "/api/v1/dataset/images/smoke/cloud-image/content",
        }
    )
    reference = InferenceImageReference(
        dataset_id="nuscenes",
        dataset_version="v1.0-mini",
        split="smoke",
        image_id="cloud-image",
        bucket="label-guardian",
        object_key="datasets/official/nuscenes/v1.0-mini/smoke/frames/scene/sample/CAM_FRONT.jpg",
    )

    evaluation = await service.evaluate(
        "smoke",
        "cloud-image",
        image_override=image,
        image_reference=reference,
    )

    assert service.uses_remote_inference is True
    assert inference_client.requests == [InferenceRequest(image=reference)]
    assert agent.last_state is not None
    assert agent.last_state["image_path"] == image.image_url
    assert agent.last_state["pred_labels"] == [
        {
            "class_name": "car",
            "bbox": {"x1": 10.0, "y1": 10.0, "x2": 30.0, "y2": 30.0},
            "confidence": 0.88,
        }
    ]
    assert evaluation.model_name == "remote-yolo@2026-08-27"


@pytest.mark.asyncio
async def test_database_evaluate_remote_inference_does_not_download_image_bytes(
    tmp_path,
    postgres_async_session_factory,
    postgres_test_database,
    monkeypatch,
):
    async with postgres_async_session_factory() as session:
        image = QAImage(
            source_image_id="remote-image",
            filename="images/smoke/remote-image.jpg",
            width=100,
            height=80,
            dataset="nuscenes",
            release="v1.0-mini",
            storage_key="datasets/official/nuscenes/v1.0-mini/smoke/frames/scene/sample/CAM_FRONT.jpg",
        )
        session.add(image)
        await session.flush()
        session.add(
            QAObject(
                image_id=image.id,
                source_object_key="object-1",
                label="vehicle.car",
                xmin=10,
                ymin=10,
                xmax=30,
                ymax=30,
                review_status=QAReviewStatus.NEEDS_REVIEW,
            )
        )
        await session.commit()

    def fail_download(_image):
        raise AssertionError("App Service should not download image bytes when remote inference is enabled.")

    monkeypatch.setattr("src.api.real_dataset._download_gcs_image", fail_download)
    agent = FakeAgent()
    inference_client = FakeInferenceClient()
    service = RealDatasetService(
        tmp_path,
        dataset_backend="database",
        dataset_id="nuscenes",
        dataset_version="v1.0-mini",
        default_split="smoke",
        agent_runner=agent,
        inference_client=inference_client,
    )
    application = create_app(
        settings=Settings(
            app_env="test",
            auth_enabled=False,
            database_url=postgres_test_database.async_url,
            _env_file=None,
        ),
        db_session_factory=postgres_async_session_factory,
        real_dataset_service=service,
    )

    async with application.router.lifespan_context(application):
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            response = await client.post("/api/v1/dataset/images/smoke/remote-image/evaluate")

    assert response.status_code == 200
    assert inference_client.requests[0].image.object_key == image.storage_key
    assert response.json()["modelName"] == "remote-yolo@2026-08-27"


@pytest.mark.asyncio
async def test_persisted_report_survives_restart_and_tracks_annotation_revision(
    tmp_path,
    postgres_async_session_factory,
    postgres_test_database,
):
    _write_dataset(tmp_path)
    path = "/api/v1/dataset/images/val/000001"
    application = _app(tmp_path, postgres_async_session_factory, postgres_test_database)
    async with application.router.lifespan_context(application):
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            assert (await client.get(f"{path}/evaluation")).status_code == 404
            first = await client.post(f"{path}/evaluate?persist=true")
            assert first.status_code == 200

    # A fresh app/service has no in-memory inference cache.
    fresh_agent = FakeAgent()
    application = _app(tmp_path, postgres_async_session_factory, postgres_test_database, fresh_agent)
    async with application.router.lifespan_context(application):
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            loaded = await client.get(f"{path}/evaluation")
            assert loaded.status_code == 200
            assert loaded.json()["report"] == first.json()["report"]
            assert loaded.json()["predictions"] == first.json()["predictions"]
            assert fresh_agent.calls == 0
            document = (await client.get(f"{path}/annotations")).json()
            saved = await client.put(
                f"{path}/annotations",
                json={
                    "expectedRevision": 0,
                    "labels": document["labels"],
                    "changeNote": "Re-review",
                },
            )
            assert saved.status_code == 200
            assert (await client.get(f"{path}/evaluation")).status_code == 404
            reevaluated = await client.post(f"{path}/evaluate?persist=true")
            assert reevaluated.status_code == 200
            assert reevaluated.json()["annotationRevision"] == 1
            assert reevaluated.json()["evaluationId"] != first.json()["evaluationId"]
            latest = await client.get(f"{path}/evaluation")
            assert latest.json()["evaluationId"] == reevaluated.json()["evaluationId"]


@pytest.mark.asyncio
async def test_batch_evaluation_reports_partial_failures_and_persists_success(
    tmp_path,
    postgres_async_session_factory,
    postgres_test_database,
):
    _write_dataset(tmp_path)
    application = _app(tmp_path, postgres_async_session_factory, postgres_test_database)
    async with application.router.lifespan_context(application):
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/dataset/images/val/evaluate-batch",
                json={
                    "imageIds": ["000001", "missing"],
                    "persist": True,
                },
            )
            assert response.status_code == 200
            result = response.json()
            assert (result["count"], result["succeeded"], result["failed"]) == (2, 1, 1)
            assert [item["imageId"] for item in result["results"]] == ["000001", "missing"]
            assert result["results"][0]["evaluation"]["persisted"] is True
            assert result["results"][1]["error"]
            assert (await client.get("/api/v1/dataset/images/val/000001/evaluation")).status_code == 200


@pytest.mark.asyncio
async def test_batch_recovers_database_transaction_after_one_failed_item(
    tmp_path,
    postgres_async_session_factory,
    postgres_test_database,
    monkeypatch,
):
    from sqlalchemy import text

    from src.services.real_dataset_qa_service import RealDatasetQaService

    _write_dataset(tmp_path)
    for folder, suffix in [("images", "png"), ("labels", "txt")]:
        source = tmp_path / folder / "val" / f"000001.{suffix}"
        source.with_name(f"000002.{suffix}").write_bytes(source.read_bytes())
    original_persist = RealDatasetQaService.persist
    calls = 0

    async def fail_first(self, session, evaluation):
        nonlocal calls
        calls += 1
        if calls == 1:
            await session.execute(text("SELECT * FROM deliberately_missing_test_table"))
        return await original_persist(self, session, evaluation)

    monkeypatch.setattr(RealDatasetQaService, "persist", fail_first)
    application = _app(tmp_path, postgres_async_session_factory, postgres_test_database)
    async with application.router.lifespan_context(application):
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/dataset/images/val/evaluate-batch",
                json={
                    "imageIds": ["000001", "000002"],
                    "persist": True,
                },
            )
    assert response.status_code == 200
    result = response.json()
    assert (result["succeeded"], result["failed"]) == (1, 1)
    assert result["results"][0]["error"] == "QA evaluation failed for this image."
    assert result["results"][1]["evaluation"]["persisted"] is True


def test_explicit_product_release_uses_imported_canonical_cache_layout(tmp_path, monkeypatch):
    monkeypatch.setenv("LABEL_GUARDIAN_GCS_CACHE_ROOT", str(tmp_path))
    service = RealDatasetService(tmp_path, dataset_backend="database", dataset_id="nuscenes", dataset_version="product")
    for dataset in ("nuscenes", "kitti"):
        roots = _official_cache_roots(service, dataset, "product")
        assert roots == [(dataset, "product", tmp_path / "datasets" / "official" / dataset / "product")]
