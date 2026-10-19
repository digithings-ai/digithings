import type { Env } from "./env";
import { handleFetch } from "./http";
import { CorpusIndexWorkflow } from "./workflow";

export { CorpusIndexWorkflow };

async function start(env: Env, instanceId: string): Promise<void> {
  try {
    await env.CORPUS_INDEX_WORKFLOW.create({ id: instanceId });
  } catch (err) {
    const message = err instanceof Error ? err.message : "";
    if (!/already/i.test(message)) throw err;
    console.log(JSON.stringify({ event: "already_running", instance: instanceId }));
  }
}

export default {
  async scheduled(controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(start(env, `cron-${controller.scheduledTime}`));
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    return handleFetch(request, env, start);
  },
};
