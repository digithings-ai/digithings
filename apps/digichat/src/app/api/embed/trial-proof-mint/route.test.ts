import { describe, expect, it } from "vitest";
import { POST } from "./route";

function mintRequest(headers: Record<string, string>, body: unknown): Request {
  return new Request("http://localhost/api/embed/trial-proof-mint", {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

describe("trial proof mint endpoint", () => {
  it("refuses anonymous minting", async () => {
    const res = await POST(mintRequest({}, { host: "datatap.stream" }));
    expect(res.status).toBe(401);
  });
});