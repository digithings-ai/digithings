/**
 * One Durable Object container. Idle sleep is 2m. It starts on a call and
 * is not always-on. max_instances = 1 is set in wrangler.toml.
 */
import { Container } from "@cloudflare/containers";
import {
  durableObjectUnavailableResponse,
  errorMessage,
  isNonErrorRejection,
} from "@digithings/durable-object-reconnect";
import { dataPlaneEnv, type Env } from "./env";
import { RUNNER_UNAVAILABLE_DETAIL } from "./unavailable";

export const RUNNER_CONTAINER_ID = "twelvex-runner-v1";

export { RUNNER_UNAVAILABLE_DETAIL };

export class TwelveXRunnerContainer extends Container<Env> {
  defaultPort = 8080;
  requiredPorts = [8080];
  sleepAfter = "2m";
  enableInternet = true;

  override async fetch(request: Request): Promise<Response> {
    this.envVars = dataPlaneEnv(this.env);
    try {
      return await this.containerFetch(request);
    } catch (cause) {
      // A hop that rejected with a value that is not an Error (run-watch
      // DIG-4928): the @cloudflare/containers package rethrows such a value
      // verbatim from its proxy catch, so it used to leave this Durable Object
      // as an uncaught exception, and the platform recorded it with
      // `String(value)` — a thrown Date leaves nothing but a bare date in the
      // log, and the guard that should answer 503 never saw it.
      //
      // Such a value carries no message, no stack and no type, so it cannot
      // be classified. The instance could not serve the request, so the
      // client is told to come back: the same contract the Worker gives when
      // the instance itself is gone. The request is NOT replayed — a value
      // that came out of the hop says nothing about whether it reached the
      // container, so a second attempt could run the job twice.
      if (!isNonErrorRejection(cause)) {
        // A real Error keeps its own behaviour: it is rethrown unchanged, so
        // an unrelated failure is never masked by this answer.
        throw cause;
      }
      console.error(
        "twelvex-runner: the container hop rejected with a value that is not an Error:",
        errorMessage(cause),
      );
      return durableObjectUnavailableResponse(RUNNER_UNAVAILABLE_DETAIL);
    }
  }
}
