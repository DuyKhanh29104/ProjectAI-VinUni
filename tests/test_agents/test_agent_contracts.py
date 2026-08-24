import pytest
from pydantic import ValidationError

from src.models.agent_schemas import BBox, LabelQARequest, QAIssue


def test_agent_request_supports_file_resolution_or_supplied_labels():
    file_request = LabelQARequest(image_path="frame.png", label_path="frame.xml")
    supplied_request = LabelQARequest(
        image_path="frame.png",
        gt_labels=[{"class_name": "car", "bbox": {"x1": 0, "y1": 0, "x2": 10, "y2": 10}}],
        pred_labels=[],
    )

    assert file_request.gt_labels is None
    assert supplied_request.gt_labels is not None
    assert supplied_request.pred_labels == []


def test_bbox_rejects_zero_or_negative_area():
    with pytest.raises(ValidationError, match="positive area"):
        BBox(x1=1, y1=1, x2=1, y2=2)


def test_loose_bbox_contract_preserves_non_blocking_flag():
    issue = QAIssue.model_validate(
        {"issue_type": "loose_bbox", "severity": "low", "blocking": False}
    )

    assert issue.issue_type == "loose_bbox"
    assert issue.blocking is False
