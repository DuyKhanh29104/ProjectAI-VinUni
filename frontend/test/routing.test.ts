import assert from "node:assert/strict";
import test from "node:test";
import {
  pathForDatasetView,
  pathForView,
  viewFromPath,
} from "../src/config/routing.ts";

test("clean URLs map to the expected application views", () => {
  assert.equal(viewFromPath("/"), "overview");
  assert.equal(viewFromPath("/qa-queue"), "qa-queue");
  assert.equal(viewFromPath("/qa-cases"), "qa-cases");
  assert.equal(viewFromPath("/real-data"), "overview");
  assert.equal(viewFromPath("/cases/LG-0001"), "case-detail");
  assert.equal(viewFromPath("/unknown"), "overview");
});

test("application views resolve to React Router paths", () => {
  assert.equal(pathForView("overview"), "/");
  assert.equal(pathForView("qa-queue"), "/qa-queue");
  assert.equal(pathForView("qa-cases"), "/qa-cases");
  assert.equal(pathForView("reports"), "/reports");
});

test("top-level API navigation keeps only the dataset scope", () => {
  assert.equal(
    pathForDatasetView("qa-cases", "nuscenes"),
    "/qa-cases?dataset=nuscenes",
  );
  assert.equal(pathForDatasetView("qa-queue"), "/qa-queue");
});
