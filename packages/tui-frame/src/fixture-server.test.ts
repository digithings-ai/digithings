import { describe, expect, test } from "bun:test";

import { startFixtureApi } from "./fixture-server.ts";

describe("the fixture API", () => {
  test("it serves the routes it is given on a loopback URL", async () => {
    const api = await startFixtureApi({
      route: (pathname) =>
        pathname === "/api/thing"
          ? { status: 200, body: { thing: 1 } }
          : { status: 404, body: { error: { code: "not_found" } } },
    });
    try {
      expect(api.url).toBe(`http://127.0.0.1:${api.port}`);
      const found = await fetch(`${api.url}/api/thing`);
      expect(found.status).toBe(200);
      expect(await found.json()).toEqual({ thing: 1 });

      const missing = await fetch(`${api.url}/elsewhere`);
      expect(missing.status).toBe(404);
      expect(await missing.json()).toEqual({ error: { code: "not_found" } });
    } finally {
      await api.close();
    }
  });

  test("two exporters at once get separate ports and both answer", async () => {
    // The defect this replaces: a fixed port made the second exporter throw
    // because the first still held the port.
    const first = await startFixtureApi({
      route: () => ({ status: 200, body: { source: "first" } }),
    });
    const second = await startFixtureApi({
      route: () => ({ status: 200, body: { source: "second" } }),
    });
    try {
      expect(first.port).not.toBe(second.port);
      const [a, b] = await Promise.all([
        fetch(`${first.url}/anything`),
        fetch(`${second.url}/anything`),
      ]);
      expect(await a.json()).toEqual({ source: "first" });
      expect(await b.json()).toEqual({ source: "second" });
    } finally {
      await Promise.all([first.close(), second.close()]);
    }
  });

  test("it binds the port it is told to", async () => {
    // Port 0 is the default, but an explicit port must still work for a caller
    // that wants a known one.
    const probe = await startFixtureApi({
      route: () => ({ status: 200, body: {} }),
    });
    const port = probe.port;
    await probe.close();
    const again = await startFixtureApi({
      port,
      route: () => ({ status: 200, body: { bound: port } }),
    });
    try {
      expect(again.port).toBe(port);
      expect(await (await fetch(`${again.url}/`)).json()).toEqual({ bound: port });
    } finally {
      await again.close();
    }
  });
});
