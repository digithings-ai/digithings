/**
 * /api/mcp-proxy/<label> — schema-normalizing MCP passthrough (DC-18).
 *
 * Off unless `DIGICHAT_MCP_SCHEMA_PROXY` maps `<label>` to an upstream MCP URL
 * (server-only env, e.g. `{"tools":"https://mcp.example.com/"}`); an unknown or
 * unconfigured label answers 404. See `src/lib/mcp/schema-proxy.ts`.
 */
import { proxySchemaNormalizedMcp } from "@/lib/mcp/schema-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ label: string }> };

async function handle(req: Request, ctx: Ctx): Promise<Response> {
  const { label } = await ctx.params;
  return proxySchemaNormalizedMcp(req, label);
}

export const GET = handle;
export const POST = handle;
export const DELETE = handle;
