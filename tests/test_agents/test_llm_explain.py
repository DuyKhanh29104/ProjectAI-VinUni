import pytest

from src.agents.nodes import llm_explain


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
    assert "khác class" in result["flagged_issues"][0]["explanation"]
    assert result["flagged_issues"][0]["suggested_fix"]
    assert result["metadata"]["llm_explain_fallback_reason"] == "quota unavailable"


@pytest.mark.asyncio
async def test_missing_llm_configuration_also_uses_fallback(monkeypatch: pytest.MonkeyPatch):
    def missing_configuration():
        raise RuntimeError("GOOGLE_API_KEY is required")

    monkeypatch.setattr(llm_explain, "get_agent_llm", missing_configuration)
    issue = {
        "label_id": None,
        "issue_type": "missing_label",
        "severity": "medium",
        "evidence": {"confidence": 0.7},
    }

    result = await llm_explain.llm_explain_node({"image_path": "fixture.png", "flagged_issues": [issue]})

    assert result["flagged_issues"][0]["issue_type"] == "missing_label"
    assert "YOLO phát hiện" in result["flagged_issues"][0]["explanation"]
    assert result["metadata"]["llm_explain_fallback_reason"] == "GOOGLE_API_KEY is required"
