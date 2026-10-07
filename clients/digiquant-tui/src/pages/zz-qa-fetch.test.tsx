import { test } from "bun:test";
(async () => {
  (globalThis as unknown as { fetch: unknown }).fetch = async () =>
    new Response(JSON.stringify({ status: "ok", data: { sessions: [] } }), {
      status: 200, headers: { "content-type": "application/json" },
    });
  const res = await (globalThis.fetch as (u: string) => Promise<Response>)("http://x/fx/sessions");
  console.log("status", res.status, await res.json());
})();
