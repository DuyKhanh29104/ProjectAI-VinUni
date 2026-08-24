import assert from "node:assert/strict";
import test from "node:test";
import { filterAndSortFindings } from "../src/domain/queueUtils.ts";
import { canEditAnnotation, canSubmitAnnotatorFeedback } from "../src/domain/permissions.ts";
import { createInitialMockState } from "../src/data/mockData.ts";
import { MockRepository } from "../src/state/mockRepository.ts";

test("QA Queue filters by dataset/status/risk and sorts by priority or risk", () => {
  const state = createInitialMockState();
  for (const finding of state.findings) {
    assert.ok(finding.datasetVersion);
    assert.ok(finding.qaRunId);
  }
  const assignedCase = state.findings.find((finding) => finding.id === "finding-006");
  assert.ok(assignedCase);
  assert.equal(canEditAnnotation(assignedCase, "reviewer", "user-reviewer"), true);
  assert.equal(canEditAnnotation(assignedCase, "annotator", "user-annotator"), true);
  assert.equal(canEditAnnotation(assignedCase, "admin", "user-admin"), false);
  assert.equal(canSubmitAnnotatorFeedback(assignedCase, "annotator", "user-reviewer"), false);
  const sceneIds = new Set(state.scenes.filter((scene) => scene.datasetId === state.selectedDatasetId).map((scene) => scene.id));
  const filtered = filterAndSortFindings(state.findings, {
    query: "",
    status: "unreviewed",
    severity: "all",
    type: "all",
    sceneId: "all",
    risk: "high",
    sortBy: "priority",
    sceneIds,
  });
  assert.deepEqual(filtered.map((finding) => finding.id), ["finding-001", "finding-003"]);

  const riskSorted = filterAndSortFindings(state.findings, {
    query: "",
    status: "all",
    severity: "all",
    type: "all",
    sceneId: "all",
    risk: "all",
    sortBy: "risk",
    sceneIds,
  });
  assert.equal(riskSorted[0]?.id, "finding-003");
});

test("role switch and review actions update mock state", () => {
  const repository = new MockRepository();
  let state = repository.seed();

  state = repository.setActiveRole(state, "annotator");
  assert.equal(state.activeRole, "annotator");
  assert.equal(state.activeUserId, "user-annotator");

  state = repository.addFindingFeedback(
    state,
    "finding-006",
    "user-annotator",
    "Đã kiểm tra frame trong 2D Editor",
  );
  assert.equal(state.reviewDecisions.at(-1)?.action, "annotator_feedback");
  assert.equal(state.reviewDecisions.at(-1)?.toStatus, "skipped");

  state = repository.setFindingStatus(state, "finding-001", "in_review", "user-reviewer", "start_review");
  assert.equal(state.findings.find((finding) => finding.id === "finding-001")?.status, "in_review");
  assert.equal(state.reviewDecisions.at(-1)?.action, "start_review");

  state = repository.setFindingStatus(state, "finding-002", "rejected", "user-reviewer", "reject_finding", "False positive mock");
  assert.equal(state.findings.find((finding) => finding.id === "finding-002")?.status, "rejected");
  assert.equal(state.reviewDecisions.at(-1)?.reason, "False positive mock");
});

test("repository proposal protects original and records approval", () => {
  const repository = new MockRepository();
  let state = repository.seed();
  const original = state.annotations.find((annotation) => annotation.id === "annotation-001");
  assert.ok(original);
  const originalBox = { ...original.bbox };

  state = repository.saveProposedAnnotation(state, "annotation-001", {
    label: "van",
    bbox: { x: 260, y: 280, width: 196, height: 146 },
    trackId: "track-17-edited",
    attributes: { ...original.attributes, sourceNote: "Mock correction" },
  }, "user-annotator");

  const proposal = state.annotations.find((annotation) => annotation.id === "annotation-001::proposed");
  const unchangedOriginal = state.annotations.find((annotation) => annotation.id === "annotation-001");
  assert.equal(proposal?.layer, "proposed");
  assert.deepEqual(unchangedOriginal?.bbox, originalBox);
  assert.equal(state.reviewDecisions.at(-1)?.action, "edit_annotation");

  state = repository.approveFinding(state, "finding-001", "user-reviewer", "Approve mock correction");
  const approved = state.annotations.find((annotation) => annotation.layer === "approved" && annotation.sourceAnnotationId === "annotation-001");
  assert.equal(approved?.label, "van");
  assert.equal(state.findings.find((finding) => finding.id === "finding-001")?.status, "corrected");
});

test("QA run and rule/model configuration stay in frontend mock state", () => {
  const repository = new MockRepository();
  let state = repository.seed();
  state = repository.updateRule(state, "rule-box-iou", { enabled: false, threshold: 0.65 });
  state = repository.updateModel(state, "model-yolo-reference", { confidenceThreshold: 0.8 });
  assert.equal(state.rules.find((rule) => rule.id === "rule-box-iou")?.enabled, false);
  assert.equal(state.models.find((model) => model.id === "model-yolo-reference")?.confidenceThreshold, 0.8);

  state = repository.startQaRun(state, state.selectedDatasetId);
  assert.equal(state.qaRun.status, "running");
  assert.equal(state.qaRun.progress, 0);
  assert.match(state.qaRun.ruleVersion, /rule-track-gap/);
  for (let step = 0; step < 4; step += 1) {
    state = repository.advanceQaRun(state);
  }
  assert.equal(state.qaRun.status, "completed");
  assert.equal(state.qaRun.progress, 100);
  assert.equal(state.qaRun.processedFrames, state.qaRun.totalFrames);
});
