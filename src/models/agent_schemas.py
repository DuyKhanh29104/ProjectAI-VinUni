"""Validated contracts for the Label QA agent pipeline."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.models.base_schemas import ApiModel


class BBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float

    @model_validator(mode="after")
    def has_positive_area(self) -> "BBox":
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("bbox must have positive area")
        return self


class GroundTruthLabel(BaseModel):
    label_id: str = Field(default="", description="Stable label ID; generated when omitted")
    class_name: str = Field(min_length=1)
    bbox: BBox


class YoloPrediction(BaseModel):
    class_name: str = Field(min_length=1)
    bbox: BBox
    confidence: float = Field(ge=0.0, le=1.0)


class LabelQARequest(BaseModel):
    image_path: str = Field(min_length=1, description="Local image path for the offline agent")
    label_path: str | None = Field(default=None, description="Optional YOLO or Pascal VOC label path")
    gt_labels: list[GroundTruthLabel] | None = None
    pred_labels: list[YoloPrediction] | None = None


class QAIssueExplanation(BaseModel):
    issue_index: int = Field(ge=0)
    explanation: str
    suggested_fix: str


class QAIssueExplanationBatch(BaseModel):
    explanations: list[QAIssueExplanation]


class QAIssue(ApiModel):
    label_id: str | None = None
    issue_type: Literal[
        "wrong_class",
        "missing_label",
        "extra_or_wrong_label",
        "bbox_misaligned",
        "loose_bbox",
        "duplicate_label",
    ]
    severity: Literal["high", "medium", "low"]
    blocking: bool = True
    explanation: str = ""
    suggested_fix: str = ""
    evidence: dict = Field(default_factory=dict)


class LabelQAReport(ApiModel):
    image_path: str
    status: Literal["pass", "needs_review", "error"]
    summary: str
    metrics: dict = Field(default_factory=dict)
    issues: list[QAIssue] = Field(default_factory=list)
