/**
 * twelvex-runner — private Worker in front of one on-demand container.
 * No public hostname. digithings-cron calls POST /run/{ingest|heartbeat}.
 */
import { getContainer } from "@cloudflare/containers";
import type { Env } from "./env";
import { TwelveXRunnerContainer, RUNNER_CONTAINER_ID } from "./runner";
import { handle } from "./worker";

export { TwelveXRunnerContainer };
export { handle };

function containerBinding(env: Env): Fetcher {
  const binding = env.TWELVEX_CONTAINER as unknown as DurableObjectNamespace<TwelveXRunnerContainer>;
  return getContainer(binding, RUNNER_CONTAINER_ID);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    return handle(request, env, containerBinding(env));
  },
};
