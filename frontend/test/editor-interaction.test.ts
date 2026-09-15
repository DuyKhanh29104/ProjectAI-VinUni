import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { classColorForLabel } from "../src/utils/labelColor.ts";

test("class colors are stable, valid and distinct", () => {
  const labels = ["car", "truck", "pedestrian", "vehicle.car", "traffic_cone"];
  const colors = labels.map(classColorForLabel);

  colors.forEach((color) => assert.match(color, /^#[0-9a-f]{6}$/i));
  assert.equal(new Set(colors).size, labels.length);
  assert.equal(
    classColorForLabel("traffic_cone"),
    classColorForLabel("traffic_cone"),
  );
});

test("editor zoom keeps an anchor point and exposes themed navigation controls", () => {
  const editorSource = readFileSync(
    new URL("../src/views/AnnotatorWorkspaceView.tsx", import.meta.url),
    "utf8",
  );
  const editorStyles = readFileSync(
    new URL("../src/styles/label-editor.css", import.meta.url),
    "utf8",
  );

  assert.match(editorSource, /const zoomAtPoint =/);
  assert.match(
    editorSource,
    /anchor\.x - \(\(anchor\.x - current\.x\) \/ zoom\) \* boundedZoom/,
  );
  assert.match(editorSource, /event\.button === 2/);
  assert.doesNotMatch(editorSource, /event\.button === 1/);
  assert.match(
    editorSource,
    /onContextMenu=\{\(event\) => event\.preventDefault\(\)\}/,
  );
  assert.match(editorSource, /className="editor-zoom-slider"/);
  assert.match(editorSource, /className="editor-nav-selectors"/);
  assert.match(editorSource, /className="editor-camera-strip"/);
  assert.match(editorStyles, /::-webkit-slider-thumb/);
  assert.match(editorStyles, /::-webkit-scrollbar-thumb/);
  assert.match(
    editorStyles,
    /\.editor-save-note-section textarea[\s\S]*?color: #fff;[\s\S]*?background: #070b11;/,
  );
  assert.match(
    editorStyles,
    /\.editor-box\.is-selected > rect\s*{[\s\S]*?fill: transparent;[\s\S]*?stroke: #ff9f1c;[\s\S]*?stroke-dasharray: none;/,
  );
});

test("editor is always editable and reserves the center panel for the canvas", () => {
  const editorSource = readFileSync(
    new URL("../src/views/AnnotatorWorkspaceView.tsx", import.meta.url),
    "utf8",
  );
  const editorStyles = readFileSync(
    new URL("../src/styles/label-editor.css", import.meta.url),
    "utf8",
  );

  assert.doesNotMatch(editorSource, /editor-mode-switch/);
  assert.doesNotMatch(editorSource, /setMode\(/);
  assert.doesNotMatch(editorSource, /mode === "review"/);
  assert.doesNotMatch(editorSource, /className="editor-detail-tabs"/);
  assert.doesNotMatch(editorSource, /useAnnotationHistoryQuery/);
  assert.doesNotMatch(editorSource, /useRestoreAnnotationsMutation/);
  assert.match(editorSource, /className={`editor-validation-status/);
  assert.match(
    editorStyles,
    /\.editor-center-panel\s*{[\s\S]*?grid-template-rows: 42px minmax\(260px, 1fr\);/,
  );
});
