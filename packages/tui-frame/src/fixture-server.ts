/**
 * The fixture API every recorded-frame exporter reads through (DIG-2698,
 * ADR D7).
 *
 * A recorded frame is a shipped artifact, so it must not be captured against a
 * live backend: it would commit whatever the data was that day, and it would
 * not reproduce. Each client serves deterministic payloads from here instead.
 *
 * The port is ephemeral by default. A fixed port made two exporters collide:
 * the second `listen()` threw while the first run held the port. A server that
 * binds port 0 gets a free port from the kernel, and `url` names it, so the
 * client can point itself at this run's server before the client module loads.
 */

import { createServer } from "node:http";

/** What a fixture route answers. */
export type FixtureAnswer = {
  status: number;
  body: unknown;
};

/**
 * Answer one request by pathname. Return the client's own error answer for a
 * route that does not exist, so the status and body shape stay the client's
 * contract.
 */
export type FixtureRoute = (pathname: string) => FixtureAnswer;

/** A running fixture API. */
export type FixtureApi = {
  /** The base URL this run bound, e.g. `http://127.0.0.1:54321`. */
  url: string;
  /** The port this run bound. */
  port: number;
  /** Stop the server and release the port. */
  close: () => Promise<void>;
};

export type FixtureServerOptions = {
  /** Answers every request. */
  route: FixtureRoute;
  /**
   * Port to bind. Default 0: the kernel picks a free port, so two exporters
   * can run at once.
   */
  port?: number;
  /** Bind address. Default `127.0.0.1`: a fixture never listens off-host. */
  hostname?: string;
  /**
   * Do not hold the process open. A one-shot exporter exits on its own; a test
   * process that keeps one fixture for several captures must still be able to
   * end.
   */
  unref?: boolean;
};

/** Start the fixture API and report the URL it actually bound. */
export async function startFixtureApi(
  options: FixtureServerOptions,
): Promise<FixtureApi> {
  const hostname = options.hostname ?? "127.0.0.1";
  const server = createServer((request, response) => {
    const pathname = new URL(request.url ?? "/", `http://${hostname}`).pathname;
    const answer = options.route(pathname);
    response.writeHead(answer.status, { "content-type": "application/json" });
    response.end(JSON.stringify(answer.body));
  });

  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(options.port ?? 0, hostname, () => resolve());
  });

  const address = server.address();
  if (address === null || typeof address === "string") {
    server.close();
    throw new Error("the fixture API did not bind a TCP port");
  }
  if (options.unref) server.unref();

  return {
    url: `http://${hostname}:${address.port}`,
    port: address.port,
    close: () =>
      new Promise<void>((resolve) => {
        // The client may keep the connection alive, so the sockets go first or
        // `close()` never calls back.
        server.closeAllConnections?.();
        server.close(() => resolve());
      }),
  };
}
