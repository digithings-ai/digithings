/**
 * The detail the client gets when the runner could not serve the request.
 *
 * The Durable Object and the Worker in front of it answer the same contract
 * for the same condition, so the wording lives here and both read it: two
 * copies of the string would drift apart and a client would then see two
 * different answers for one condition.
 */
export const RUNNER_UNAVAILABLE_DETAIL =
  "the runner's Durable Object instance was not available; retry later";
