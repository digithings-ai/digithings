/**
 * One Durable Object container. Idle sleep is 2m. It starts on a call and
 * is not always-on. max_instances = 1 is set in wrangler.toml.
 */
import { Container } from "@cloudflare/containers";
import { dataPlaneEnv, type Env } from "./env";

export const RUNNER_CONTAINER_ID = "twelvex-runner-v1";

export class TwelveXRunnerContainer extends Container<Env> {
  defaultPort = 8080;
  requiredPorts = [8080];
  sleepAfter = "2m";
  enableInternet = true;

  override async fetch(request: Request): Promise<Response> {
    this.envVars = dataPlaneEnv(this.env);
    return this.containerFetch(request);
  }
}
