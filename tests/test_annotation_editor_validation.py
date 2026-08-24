import pytest

from src.models.real_dataset_schemas import RealDatasetBBox, RealDatasetImage, RealDatasetLabel
from src.services.annotation_editor_service import AnnotationEditorService


def _image() -> RealDatasetImage:
    return RealDatasetImage(
        id="camera-1",
        split="smoke",
        filename="camera-1.jpg",
        width=1600,
        height=900,
        label_count=0,
        labels=[],
        image_url="/api/v1/dataset/images/smoke/camera-1/content",
    )


def test_editor_validation_preserves_labels_outside_the_image() -> None:
    labels = [
        RealDatasetLabel(
            id="outside-1",
            class_name="vehicle.car",
            bbox=RealDatasetBBox(x1=-5000, y1=400, x2=-4500, y2=700),
        )
    ]

    AnnotationEditorService._validate_labels(_image(), labels)


def test_editor_validation_rejects_non_finite_coordinates() -> None:
    labels = [
        RealDatasetLabel(
            id="invalid-1",
            class_name="vehicle.car",
            bbox=RealDatasetBBox(x1=float("nan"), y1=10, x2=20, y2=30),
        )
    ]

    with pytest.raises(ValueError, match="non-finite"):
        AnnotationEditorService._validate_labels(_image(), labels)


def test_editor_change_detection_targets_only_modified_labels() -> None:
    previous = [
        {"id": "car-1", "className": "car", "bbox": {"x1": 0, "y1": 0, "x2": 10, "y2": 10}},
        {"id": "car-2", "className": "car", "bbox": {"x1": 20, "y1": 20, "x2": 30, "y2": 30}},
    ]
    current = [
        {"id": "car-1", "className": "truck", "bbox": {"x1": 0, "y1": 0, "x2": 10, "y2": 10}},
        {"id": "car-2", "className": "car", "bbox": {"x1": 20, "y1": 20, "x2": 30, "y2": 30}},
        {"id": "car-3", "className": "car", "bbox": {"x1": 40, "y1": 40, "x2": 50, "y2": 50}},
    ]

    changed, added = AnnotationEditorService._changed_label_ids(previous, current)

    assert changed == {"car-1", "car-3"}
    assert added == {"car-3"}


def test_missing_case_is_resolved_only_by_overlapping_added_label() -> None:
    evidence = {
        "issueEvidence": {
            "class_name": "car",
            "bbox": {"x1": 10, "y1": 10, "x2": 30, "y2": 30},
        }
    }

    assert AnnotationEditorService._missing_case_matches_added_label(
        evidence,
        [{"id": "new", "className": "car", "bbox": {"x1": 12, "y1": 12, "x2": 28, "y2": 28}}],
    )
    assert not AnnotationEditorService._missing_case_matches_added_label(
        evidence,
        [{"id": "other", "className": "car", "bbox": {"x1": 100, "y1": 100, "x2": 120, "y2": 120}}],
    )
