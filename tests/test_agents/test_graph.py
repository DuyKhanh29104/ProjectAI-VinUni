import pytest
from PIL import Image

from src.agents.graph import agent


@pytest.mark.asyncio
async def test_agent_accepts_supplied_labels_without_model_or_llm():
    bbox = {"x1": 10.0, "y1": 10.0, "x2": 30.0, "y2": 30.0}
    result = await agent.ainvoke(
        {
            "image_path": "fixture.png",
            "gt_labels": [{"label_id": "gt-1", "class_name": "car", "bbox": bbox}],
            "pred_labels": [{"class_name": "car", "bbox": bbox, "confidence": 0.95}],
        }
    )

    assert result["qa_report"]["status"] == "pass"
    assert result["qa_report"]["metrics"]["f1"] == 1.0
    assert result["qa_report"]["issues"] == []


@pytest.mark.asyncio
async def test_agent_does_not_flag_ground_truth_fully_outside_image(tmp_path):
    image_path = tmp_path / "frame.png"
    Image.new("RGB", (100, 80)).save(image_path)
    result = await agent.ainvoke(
        {
            "image_path": str(image_path),
            "gt_labels": [
                {
                    "label_id": "outside",
                    "class_name": "car",
                    "bbox": {"x1": -50.0, "y1": 10.0, "x2": -10.0, "y2": 30.0},
                }
            ],
            "pred_labels": [],
        }
    )

    assert result["qa_report"]["status"] == "pass"
    assert result["qa_report"]["issues"] == []
    assert result["qa_report"]["metrics"]["ground_truth_total"] == 1
    assert result["qa_report"]["metrics"]["ground_truth_evaluated"] == 0
    assert result["qa_report"]["metrics"]["ground_truth_excluded_outside"] == 1


@pytest.mark.asyncio
async def test_agent_returns_error_report_for_invalid_supplied_labels():
    result = await agent.ainvoke(
        {
            "image_path": "fixture.png",
            "gt_labels": [{"class_name": "car", "bbox": {"x1": 1.0}}],
            "pred_labels": [],
        }
    )

    assert result["qa_report"]["status"] == "error"
    assert "bbox" in result["qa_report"]["summary"]


@pytest.mark.asyncio
async def test_agent_keeps_review_result_when_llm_is_not_configured(monkeypatch: pytest.MonkeyPatch):
    def missing_configuration():
        raise RuntimeError("No Label QA LLM credential configured")

    monkeypatch.setattr("src.agents.nodes.llm_explain.get_agent_llm", missing_configuration)
    bbox = {"x1": 10.0, "y1": 10.0, "x2": 30.0, "y2": 30.0}
    result = await agent.ainvoke(
        {
            "image_path": "fixture.png",
            "gt_labels": [{"label_id": "gt-1", "class_name": "car", "bbox": bbox}],
            "pred_labels": [{"class_name": "truck", "bbox": bbox, "confidence": 0.95}],
        }
    )

    assert result["qa_report"]["status"] == "needs_review"
    assert result["qa_report"]["issues"][0]["issue_type"] == "wrong_class"
    assert "khác class" in result["qa_report"]["issues"][0]["explanation"]
