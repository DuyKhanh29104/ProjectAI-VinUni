import pytest

from src.agents.nodes import llm_explain
from src.models.agent_schemas import QAIssueExplanationBatch


class _FailingStructuredLLM:
    async def ainvoke(self, _messages):
        raise RuntimeError("quota unavailable")


class _FailingLLM:
    def with_structured_output(self, _schema):
        return _FailingStructuredLLM()


@pytest.mark.asyncio
async def test_llm_failure_keeps_rule_based_issues(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(llm_explain, "get_agent_llm", lambda: _FailingLLM())
    issue = {
        "label_id": "gt-1",
        "issue_type": "wrong_class",
        "severity": "high",
        "evidence": {"iou": 0.9},
    }

    result = await llm_explain.llm_explain_node(
        {"image_path": "fixture.png", "metrics": {"f1": 0.5}, "flagged_issues": [issue]}
    )

    assert result["flagged_issues"][0]["issue_type"] == "wrong_class"
    assert "loại đối tượng" in result["flagged_issues"][0]["explanation"]
    assert result["flagged_issues"][0]["suggested_fix"]
    assert result["metadata"]["llm_explain_fallback_reason"] == "quota unavailable"


@pytest.mark.asyncio
async def test_missing_llm_configuration_also_uses_fallback(monkeypatch: pytest.MonkeyPatch):
    def missing_configuration():
        raise RuntimeError("OPENAI_API_KEY is required")

    monkeypatch.setattr(llm_explain, "get_agent_llm", missing_configuration)
    issue = {
        "label_id": None,
        "issue_type": "missing_label",
        "severity": "medium",
        "evidence": {"confidence": 0.7},
    }

    result = await llm_explain.llm_explain_node({"image_path": "fixture.png", "flagged_issues": [issue]})

    assert result["flagged_issues"][0]["issue_type"] == "missing_label"
    assert "70%" in result["flagged_issues"][0]["explanation"]
    assert result["metadata"]["llm_explain_fallback_reason"] == "OPENAI_API_KEY is required"


@pytest.mark.parametrize("omit_issue", [False, True])
async def test_explanation_locates_object_and_preserves_rules(monkeypatch, omit_issue):
    messages = []

    class LLM:
        def with_structured_output(self, schema):
            return self

        async def ainvoke(self, prompt):
            messages.extend(prompt)
            if not omit_issue:
                raise RuntimeError("offline")
            return QAIssueExplanationBatch(explanations=[])

    monkeypatch.setattr(llm_explain, "get_agent_llm", LLM)
    issue = {
        "label_id": "gt-1",
        "issue_type": "loose_bbox",
        "severity": "low",
        "blocking": False,
        "evidence": {"gt_class": "car", "iou": 0.7},
    }
    result = await llm_explain.llm_explain_node(
        {
            "flagged_issues": [issue],
            "gt_labels": [{"label_id": "gt-1", "class_name": "car", "bbox": {"x1": 10, "y1": 10, "x2": 20, "y2": 20}}],
            "metadata": {"label_scope": {"image_width": 100, "image_height": 100}},
        }
    )
    enriched = result["flagged_issues"][0]
    assert {key: enriched[key] for key in issue} == issue
    assert "phía trên bên trái" in enriched["explanation"]
    assert "phía trên bên trái" in enriched["suggested_fix"]
    assert "car" in enriched["explanation"]
    assert "70%" in enriched["explanation"]
    assert "phần còn lại là nền" not in enriched["explanation"]
    assert "phía trên bên trái" in messages[1]["content"]


def test_unknown_image_size_keeps_coordinates_without_inventing_position():
    issue = {
        "issue_type": "missing_label",
        "evidence": {
            "class_name": "car",
            "confidence": 0.7,
            "bbox": {"x1": 10, "y1": 20, "x2": 30, "y2": 40},
        },
    }
    result = llm_explain._local_fallback_issue(issue)
    assert "x: 10-30" in result["explanation"]
    assert "bên trái" not in result["explanation"]
