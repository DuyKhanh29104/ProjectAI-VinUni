import assert from "node:assert/strict";
import test from "node:test";
import {
  LabelGuardianApiError,
  isApiDataSourceEnabled,
  labelGuardianApiV1,
} from "../src/api/labelGuardianApi.ts";
import { isSupabaseAuthEnabled } from "../src/auth/supabase.ts";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

test("missing build variables fail closed to API and Supabase modes", () => {
  assert.equal(isApiDataSourceEnabled(), true);
  assert.equal(isSupabaseAuthEnabled(), true);
});

test("authenticated profile request sends the supplied bearer token", async () => {
  const originalFetch = globalThis.fetch;
  let authorization = "";
  globalThis.fetch = async (_input, init) => {
    authorization = new Headers(init?.headers).get("Authorization") ?? "";
    return json({
      id: "user-1",
      email: "user@example.com",
      displayName: "User",
      role: "annotator",
      disabled: false,
    });
  };
  try {
    await labelGuardianApiV1.getMyProfile("access-token");
    assert.equal(authorization, "Bearer access-token");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("QA case client uses built-in status endpoint", async () => {
  const originalFetch = globalThis.fetch;
  let request: { url: string; method: string; body?: string } | undefined;
  globalThis.fetch = async (input, init) => {
    request = {
      url: String(input),
      method: init?.method ?? "GET",
      body: typeof init?.body === "string" ? init.body : undefined,
    };
    return json({ id: "LG-1", status: "confirmed" });
  };
  try {
    const result = await labelGuardianApiV1.updateQaCaseStatus(
      "LG-1",
      "confirmed",
      "reviewer-1",
      "Looks good",
    );
    assert.equal(request?.url, "/api/v1/qa-cases/LG-1/status");
    assert.equal(request?.method, "POST");
    assert.deepEqual(JSON.parse(request?.body ?? "{}"), {
      status: "confirmed",
      actorId: "reviewer-1",
      reason: "Looks good",
    });
    assert.equal(result.status, "confirmed");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("QA case client scopes cases by dataset image", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = "";
  globalThis.fetch = async (input) => {
    requestedUrl = String(input);
    return json({ count: 0, results: [], limit: 200, offset: 0 });
  };
  try {
    await labelGuardianApiV1.listQaCases(undefined, {
      split: "smoke",
      sourceImageId: "image 1",
    });
    assert.equal(
      requestedUrl,
      "/api/v1/qa-cases?limit=200&split=smoke&sourceImageId=image+1",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("annotation client saves, reads history and restores revisions", async () => {
  const originalFetch = globalThis.fetch;
  const requests: Array<{ url: string; method: string; body?: string }> = [];
  globalThis.fetch = async (input, init) => {
    requests.push({
      url: String(input),
      method: init?.method ?? "GET",
      body: typeof init?.body === "string" ? init.body : undefined,
    });
    if (String(input).endsWith("/history"))
      return json({ count: 1, results: [{ revision: 1, labelCount: 1 }] });
    return json({ revision: requests.length, labels: [] });
  };
  try {
    await labelGuardianApiV1.getImageAnnotations("val", "image 1");
    await labelGuardianApiV1.saveImageAnnotations("val", "image 1", {
      expectedRevision: 0,
      labels: [],
      actorId: "annotator",
    });
    const history = await labelGuardianApiV1.getImageAnnotationHistory(
      "val",
      "image 1",
    );
    await labelGuardianApiV1.restoreImageAnnotations("val", "image 1", {
      expectedRevision: 1,
      targetRevision: 0,
    });
    assert.deepEqual(
      requests.map(({ url, method }) => [url, method]),
      [
        ["/api/v1/dataset/images/val/image%201/annotations", "GET"],
        ["/api/v1/dataset/images/val/image%201/annotations", "PUT"],
        ["/api/v1/dataset/images/val/image%201/annotations/history", "GET"],
        ["/api/v1/dataset/images/val/image%201/annotations/restore", "POST"],
      ],
    );
    assert.equal(history.count, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("API client preserves backend conflict detail", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () =>
    json({ detail: "Expected revision 0, current revision is 1" }, 409);
  try {
    await assert.rejects(
      () =>
        labelGuardianApiV1.saveImageAnnotations("val", "1", {
          expectedRevision: 0,
          labels: [],
        }),
      (error: unknown) => {
        assert.ok(error instanceof LabelGuardianApiError);
        assert.equal(error.status, 409);
        assert.match(error.message, /current revision is 1/);
        return true;
      },
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("dataset client lists frames and evaluates through API V1", async () => {
  const originalFetch = globalThis.fetch;
  const requests: Array<{ url: string; method: string }> = [];
  globalThis.fetch = async (input, init) => {
    requests.push({ url: String(input), method: init?.method ?? "GET" });
    return json(
      String(input).includes("evaluate")
        ? { report: { status: "pass" } }
        : { count: 0, results: [] },
    );
  };
  try {
    await labelGuardianApiV1.listRealDatasetImages("val");
    await labelGuardianApiV1.listRealDatasetFrameSamples("val");
    const evaluated = await labelGuardianApiV1.evaluateRealDatasetImage(
      "val",
      "000001",
    );
    assert.equal(
      requests[2]?.url,
      "/api/v1/dataset/images/val/000001/evaluate?force=false&persist=true",
    );
    assert.equal(requests[2]?.method, "POST");
    assert.equal(evaluated.report.status, "pass");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("dataset client lets the backend choose its configured default split", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = "";
  globalThis.fetch = async (input) => {
    requestedUrl = String(input);
    return json({ count: 0, results: [], split: "smoke" });
  };
  try {
    await labelGuardianApiV1.listRealDatasetFrameSamples(undefined);
    assert.equal(
      requestedUrl,
      "/api/v1/dataset/frame-samples?limit=100&offset=0",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("dataset client scopes frame samples by sequence and page size", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = "";
  globalThis.fetch = async (input) => {
    requestedUrl = String(input);
    return json({ count: 0, results: [], split: "product" });
  };
  try {
    await labelGuardianApiV1.listRealDatasetFrameSamples(
      "product",
      20,
      undefined,
      "nuscenes",
      "scene-001",
      10,
    );
    assert.equal(
      requestedUrl,
      "/api/v1/dataset/frame-samples?limit=10&offset=20&split=product&dataset=nuscenes&sequence_id=scene-001",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("dataset client lists frame sequences without loading frame payloads", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = "";
  globalThis.fetch = async (input) => {
    requestedUrl = String(input);
    return json(["scene-001", "scene-002"]);
  };
  try {
    const sequences = await labelGuardianApiV1.listRealDatasetFrameSequences(
      "product",
      undefined,
      "nuscenes",
    );
    assert.deepEqual(sequences, ["scene-001", "scene-002"]);
    assert.equal(
      requestedUrl,
      "/api/v1/dataset/frame-sequences?split=product&dataset=nuscenes",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("persisted evaluation treats only a missing report as empty", async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => json({ detail: "No evaluation" }, 404);
    assert.equal(await labelGuardianApiV1.getRealDatasetImageEvaluation("product", "frame"), null);
    globalThis.fetch = async () => json({ detail: "Forbidden" }, 403);
    await assert.rejects(
      labelGuardianApiV1.getRealDatasetImageEvaluation("product", "frame"),
      (error: unknown) => error instanceof LabelGuardianApiError && error.status === 403,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("batch evaluation sends one request with explicit persistence", async () => {
  const originalFetch = globalThis.fetch;
  const requests: Array<{ url: string; method?: string; body: unknown }> = [];
  globalThis.fetch = async (input, init) => {
    requests.push({ url: String(input), method: init?.method, body: JSON.parse(String(init?.body)) });
    return json({ count: 2, succeeded: 2, failed: 0, results: [] });
  };
  try {
    await labelGuardianApiV1.evaluateRealDatasetImagesBatch("train/val", ["one", "two"], true, true);
    assert.deepEqual(requests, [{
      url: "/api/v1/dataset/images/train%2Fval/evaluate-batch", method: "POST",
      body: { imageIds: ["one", "two"], force: true, persist: true },
    }]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
