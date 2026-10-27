import { afterEach, describe, expect, it, vi } from "vitest";
import {
  SupabaseConfigError,
  SupabaseError,
  refreshTraceRow,
  resolveWorkspaceId,
  restRequest,
  supabaseConfig,
  upsertRows,
} from "./supabase";

const ENV = {
  SUPABASE_URL: "https://core.example.supabase.co",
  CORE_SUPABASE_SERVICE_KEY: "service-role-key",
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("supabaseConfig", () => {
  it("returns the trimmed project and key", () => {
    expect(
      supabaseConfig({
        SUPABASE_URL: " https://x.supabase.co/ ",
        CORE_SUPABASE_SERVICE_KEY: " k ",
      }),
    ).toEqual({ url: "https://x.supabase.co", key: "k" });
  });

  it("names what is missing instead of falling back to a default", () => {
    expect(() => supabaseConfig({})).toThrow(SupabaseConfigError);
    expect(() => supabaseConfig({ SUPABASE_URL: "https://x" })).toThrow(
      "CORE_SUPABASE_SERVICE_KEY is unset",
    );
    expect(() => supabaseConfig({ CORE_SUPABASE_SERVICE_KEY: "k" })).toThrow(
      "SUPABASE_URL is unset",
    );
  });
});

describe("restRequest", () => {
  it("sends the service role as apikey and bearer, never in the URL", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, []));
    vi.stubGlobal("fetch", fetchMock);

    await restRequest(ENV, "workspaces?select=id");

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://core.example.supabase.co/rest/v1/workspaces?select=id");
    expect(url).not.toContain("service-role-key");
    const headers = init.headers as Headers;
    expect(headers.get("apikey")).toBe("service-role-key");
    expect(headers.get("authorization")).toBe("Bearer service-role-key");
  });
});

describe("resolveWorkspaceId", () => {
  it("resolves a slug to the workspaces row id", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, [{ id: "workspace-uuid" }]));
    vi.stubGlobal("fetch", fetchMock);

    expect(await resolveWorkspaceId(ENV, "digithings")).toBe("workspace-uuid");
    const url = (fetchMock.mock.calls[0] as unknown as [string])[0];
    expect(url).toContain("workspaces?slug=eq.digithings&select=id&limit=1");
  });

  it("encodes the slug, so a crafted one cannot change the query", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, [{ id: "workspace-uuid" }]));
    vi.stubGlobal("fetch", fetchMock);

    await resolveWorkspaceId(ENV, "a&select=*");
    const url = (fetchMock.mock.calls[0] as unknown as [string])[0];
    expect(url).toContain("slug=eq.a%26select%3D*");
  });

  it("throws when no workspace carries the slug", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(200, [])),
    );
    await expect(resolveWorkspaceId(ENV, "nobody")).rejects.toThrow(
      "workspace not found for tenant nobody",
    );
  });

  it("throws on a PostgREST failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(500, { message: "boom", code: "XX000" })),
    );
    await expect(resolveWorkspaceId(ENV, "digithings")).rejects.toThrow(
      "PostgREST 500: boom (XX000)",
    );
  });
});

describe("refreshTraceRow", () => {
  it("posts the two function parameters to the rpc, with the service role", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await refreshTraceRow(ENV, "workspace-uuid", "0af7651916cd43dd8448eb211c80319c");

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://core.example.supabase.co/rest/v1/rpc/refresh_digitrace_trace");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      p_workspace_id: "workspace-uuid",
      p_trace_id: "0af7651916cd43dd8448eb211c80319c",
    });
    const headers = init.headers as Headers;
    expect(headers.get("authorization")).toBe("Bearer service-role-key");
  });

  it("throws with the PostgREST status, so the message retries instead of ignoring it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(404, { message: "function not found" })),
    );
    await expect(refreshTraceRow(ENV, "workspace-uuid", "trace-1")).rejects.toBeInstanceOf(
      SupabaseError,
    );
  });
});

describe("upsertRows", () => {
  it("POSTs an upsert with the natural key as the conflict target", async () => {
    const fetchMock = vi.fn(async () => new Response("", { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);

    await upsertRows(ENV, "digitrace_traces", [{ trace_id: "t" }], "workspace_id,trace_id");

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(
      "https://core.example.supabase.co/rest/v1/digitrace_traces?on_conflict=workspace_id%2Ctrace_id",
    );
    expect(init.method).toBe("POST");
    expect((init.headers as Headers).get("prefer")).toContain("resolution=merge-duplicates");
    expect((init.headers as Headers).get("content-type")).toBe("application/json");
    expect(init.body).toBe(JSON.stringify([{ trace_id: "t" }]));
  });

  it("does not call PostgREST at all for an empty row list", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await upsertRows(ENV, "digitrace_sessions", [], "workspace_id,session_id");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("throws a SupabaseError that carries the status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(409, { message: "conflict" })),
    );
    await expect(
      upsertRows(ENV, "digitrace_spans_index", [{}], "workspace_id,trace_id,span_id"),
    ).rejects.toBeInstanceOf(SupabaseError);
  });

  it("keeps row values out of the error, because they are span content", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(400, {
          message: "invalid input syntax",
          code: "22P02",
          details: "Failing row contains (secret prompt text).",
          hint: "secret prompt text",
        }),
      ),
    );

    await expect(upsertRows(ENV, "digitrace_spans_index", [{}], "workspace_id")).rejects.toThrow(
      /^PostgREST 400: invalid input syntax \(22P02\)$/,
    );
  });

  it("does not throw the service key into a failure message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("not json", { status: 502 })),
    );
    const error = await upsertRows(ENV, "t", [{}], "k").catch((caught: Error) => caught);
    expect((error as Error).message).toBe("PostgREST 502");
    expect((error as Error).message).not.toContain("service-role-key");
  });
});
