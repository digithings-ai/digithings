/**
 * digithings-cron — org-wide Cloudflare Worker production clocks (#3579).
 * Cron Triggers fire workflow_dispatch / repository_dispatch on the default branch.
 */
import { dispatch } from "./dispatch";
import type { Env } from "./env";
import { shouldDispatchAtOpen } from "./et-open";
import { jobsForCron, type Job } from "./jobs";

async function runJobsForCron(
  cron: string,
  scheduledTime: number,
  env: Env,
  ctx: ExecutionContext,
): Promise<{ started: string[]; skipped: string[] }> {
  const jobs = jobsForCron(cron);
  const started: string[] = [];
  const skipped: string[] = [];
  const pending: Promise<unknown>[] = [];

  if (jobs.length === 0) {
    console.error(JSON.stringify({ cron, error: "unmapped_cron" }));
  }
  for (const job of jobs) {
    if (job.etOpenGate && !shouldDispatchAtOpen(cron, scheduledTime)) {
      skipped.push(job.id);
      console.log(
        JSON.stringify({
          cron,
          repo: job.repo,
          job: job.id,
          github_status: null,
          dry_run: env.DRY_RUN === "1",
          skipped: "et_open_gate",
        }),
      );
      continue;
    }
    started.push(job.id);
    pending.push(
      dispatch(env, job, cron).catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : String(err);
        console.error(JSON.stringify({ cron, job: job.id, error: msg }));
        throw err;
      }),
    );
  }
  if (pending.length > 0) {
    ctx.waitUntil(Promise.all(pending));
  }
  return { started, skipped };
}

function normalizePath(pathname: string): string {
  if (pathname.length > 1 && pathname.endsWith("/")) {
    return pathname.slice(0, -1);
  }
  return pathname || "/";
}

export default {
  async scheduled(
    controller: ScheduledController,
    env: Env,
    ctx: ExecutionContext,
  ): Promise<void> {
    await runJobsForCron(controller.cron, controller.scheduledTime, env, ctx);
  },

  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const path = normalizePath(url.pathname);

    if (request.method === "GET" && (path === "/" || path === "/healthz")) {
      return Response.json(
        {
          ok: true,
          service: "digithings-cron",
          dry_run: env.DRY_RUN === "1",
        },
        { status: 200 },
      );
    }

    if (request.method === "POST" && path === "/kick") {
      if (!env.CRON_KICK_SECRET) {
        return new Response("Not Found", { status: 404 });
      }
      const auth = request.headers.get("Authorization") ?? "";
      const expected = `Bearer ${env.CRON_KICK_SECRET}`;
      if (auth !== expected) {
        return new Response("Unauthorized", { status: 401 });
      }
      let cron = "";
      try {
        const body = (await request.json()) as { cron?: string };
        cron = typeof body.cron === "string" ? body.cron : "";
      } catch {
        return Response.json({ error: "invalid_json" }, { status: 400 });
      }
      if (!cron) {
        return Response.json({ error: "cron_required" }, { status: 400 });
      }
      const result = await runJobsForCron(cron, Date.now(), env, ctx);
      return Response.json({ ok: true, cron, ...result }, { status: 200 });
    }

    return new Response("Not Found", { status: 404 });
  },
};

export type { Env, Job };
