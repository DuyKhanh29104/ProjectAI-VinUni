from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.models.inference_schemas import InferenceBatchRequest, InferenceImageReference
from src.services.inference_client import InferenceClientError, RemoteInferenceClient


def _image(image_id: str = "1") -> InferenceImageReference:
    return InferenceImageReference(
        dataset_id="nuscenes",
        dataset_version="mini",
        split="val",
        image_id=image_id,
        bucket="test-bucket",
        object_key=f"images/{image_id}.jpg",
    )


async def _detect(monkeypatch, images):
    client = RemoteInferenceClient(base_url="https://inference.example")
    monkeypatch.setattr(
        client,
        "_post",
        AsyncMock(
            return_value={
                "model_name": "yolo",
                "model_version": "test",
                "results": [{"image": image.model_dump(), "detections": []} for image in images],
            }
        ),
    )
    return await client.detect_batch(InferenceBatchRequest(images=[_image(), _image("2")]))


@pytest.mark.parametrize(
    "field,value",
    [
        ("dataset_id", "kitti"),
        ("dataset_version", "other"),
        ("split", "train"),
        ("image_id", "other"),
        ("bucket", "other"),
        ("object_key", "wrong.jpg"),
    ],
)
async def test_batch_rejects_wrong_image_identity(monkeypatch, field, value):
    with pytest.raises(InferenceClientError, match="mismatched image references"):
        await _detect(monkeypatch, [_image().model_copy(update={field: value}), _image("2")])


@pytest.mark.parametrize("ids", [["1"], ["1", "1"], ["1", "2", "3"]])
async def test_batch_rejects_missing_duplicate_or_extra_results(monkeypatch, ids):
    with pytest.raises(InferenceClientError, match="mismatched image references"):
        await _detect(monkeypatch, [_image(image_id) for image_id in ids])


async def test_batch_accepts_reordered_results(monkeypatch):
    response = await _detect(monkeypatch, [_image("2"), _image()])
    assert [item.image.image_id for item in response.results] == ["2", "1"]


@pytest.mark.parametrize("raise_error", [False, True])
async def test_batch_endpoint_sanitizes_upstream_errors(monkeypatch, raise_error):
    from src.api import real_dataset
    from src.models.inference_schemas import InferenceBatchItemResponse, InferenceBatchResponse
    from src.models.real_dataset_schemas import RealDatasetBatchEvaluationRequest

    secret_error = "provider credentials and internal object details"
    remote = AsyncMock()
    if raise_error:
        remote.detect_batch.side_effect = RuntimeError(secret_error)
    else:
        remote.detect_batch.return_value = InferenceBatchResponse(
            model_name="yolo",
            model_version="test",
            results=[InferenceBatchItemResponse(image=_image(), detections=[], error=secret_error)],
        )
    service = SimpleNamespace(inference_client=remote, evaluate=AsyncMock())
    monkeypatch.setattr(
        real_dataset,
        "_prepare_evaluation_input",
        AsyncMock(
            return_value=SimpleNamespace(image_id="1", image_reference=_image()),
        ),
    )
    response = await real_dataset.evaluate_real_dataset_images_batch(
        "val",
        RealDatasetBatchEvaluationRequest(image_ids=["1"]),
        service,
        None,
        AsyncMock(),
    )
    assert response.failed == 1
    assert response.succeeded == 0
    assert secret_error not in response.model_dump_json()
    assert response.results[0].error in {
        "Batch inference failed for this image.",
        "Inference failed for this image.",
    }
    service.evaluate.assert_not_awaited()
