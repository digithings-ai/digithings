import { describe, expect, it } from "vitest";
import { CONTAINER_UNAVAILABLE_BODY, fetchContainerWithRetry } from "./container-retry";
import { FRAME_SAFE_ERROR_HTML, frameSafeErrorResponse, isDocumentRequest } from "./frame-safe-error";

const EMBED = "https://digithings.ai/embed?host=digithings.ai&layout=page";

function frameRequest(headers: Record<string, string> = { "sec-fetch-dest": "iframe" }): Request {
  return new Request(EMBED, { headers });
}

describe("frame-safe /embed failures", () => {
  it("recognises frame and page navigations, not API fetches", () => {
    expect(isDocumentRequest(frameRequest())).toBe(true);
    expect(isDocumentRequest(frameRequest({ "sec-fetch-dest": "document" }))).toBe(true);
    expect(isDocumentRequest(frameRequest({ accept: "text/html,application/xhtml+xml" }))).toBe(true);
    expect(isDocumentRequest(frameRequest({ "sec-fetch-dest": "empty", accept: "*/*" }))).toBe(false);
  });

  it("serves the container-unreachable failure to a frame as inline HTML", async () => {
    // Mocked container: the fetch throws, as a just-restarted instance does.
    const res = frameSafeErrorResponse(
      frameRequest(),
      await fetchContainerWithRetry(frameRequest(), async () => {
        throw new Error("Network connection lost.");
      }),
    );
    expect(res.status).toBe(503);
    expect(res.headers.get("content-type")).toBe("text/html; charset=utf-8");
    expect(res.headers.get("content-disposition")).toBeNull();
    expect(res.headers.get("retry-after")).not.toBeNull();
    const body = await res.text();
    expect(body).toBe(FRAME_SAFE_ERROR_HTML);
    expect(body).not.toContain("container_unavailable");
  });

  it("drops an attachment disposition from a failed frame load", async () => {
    const upstream = new Response("boom", {
      status: 500,
      headers: {
        "content-type": "application/octet-stream",
        "content-disposition": 'attachment; filename="embed"',
      },
    });
    const res = frameSafeErrorResponse(frameRequest(), upstream);
    expect(res.status).toBe(500);
    expect(res.headers.get("content-type")).toBe("text/html; charset=utf-8");
    expect(res.headers.get("content-disposition")).toBeNull();
    expect(await res.text()).not.toContain("boom");
  });

  it("keeps an HTML error page as is", async () => {
    const page = "<!DOCTYPE html><html><body>500</body></html>";
    const upstream = new Response(page, {
      status: 500,
      headers: { "content-type": "text/html; charset=utf-8" },
    });
    const res = frameSafeErrorResponse(frameRequest(), upstream);
    expect(res).toBe(upstream);
  });

  it("leaves API callers and successful loads untouched", () => {
    const json = new Response(CONTAINER_UNAVAILABLE_BODY, { status: 503 });
    expect(frameSafeErrorResponse(frameRequest({ "sec-fetch-dest": "empty" }), json)).toBe(json);
    const ok = new Response("<html></html>", { status: 200, headers: { "content-type": "text/html" } });
    expect(frameSafeErrorResponse(frameRequest(), ok)).toBe(ok);
  });
});
