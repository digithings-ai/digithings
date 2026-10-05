import { describe, expect, it } from "vitest";
import { isEdgeOnlyPath } from "./paths";

describe("isEdgeOnlyPath", () => {
  it("marks digitrace edge health and worker-wake", () => {
    expect(isEdgeOnlyPath("/_langfuse/healthz")).toBe(true);
    expect(isEdgeOnlyPath("/_langfuse/worker-wake")).toBe(true);
  });

  it("does not treat Langfuse UI/API paths as edge-only", () => {
    expect(isEdgeOnlyPath("/")).toBe(false);
    expect(isEdgeOnlyPath("/api/public/otel")).toBe(false);
    expect(isEdgeOnlyPath("/api/public/health")).toBe(false);
  });
});
