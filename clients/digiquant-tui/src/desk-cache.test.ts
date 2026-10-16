import { expect, test } from "bun:test";

// The desk cache is shared with the web desk by relative path, the way this client already
// reaches across trees (theme.ts -> packages/ui, app.tsx -> apps/digiquant-web). This file
// exists so the shared module is exercised in the lane that consumes it: if a future edit
// reaches for React, fetch or a DOM global, `bun test` is what fails first.
import { createDeskCache } from "../../../apps/digiquant-web/lib/live/desk-cache";

test("shares one read across concurrent callers and serves it afterwards", async () => {
  const cache = createDeskCache<string>({ maxAgeMs: 1_000 });
  let reads = 0;
  let release: (value: string) => void = () => {};
  const gate = new Promise<string>((resolve) => {
    release = resolve;
  });
  const reader = () => {
    reads += 1;
    return gate;
  };

  const first = cache.load("brief", reader);
  const second = cache.load("brief", reader);
  expect(reads).toBe(1);

  release("brief-body");
  expect(await first).toBe("brief-body");
  expect(await second).toBe("brief-body");

  expect(await cache.load("brief", reader)).toBe("brief-body");
  expect(reads).toBe(1);
  expect(cache.size()).toBe(1);
});

test("re-reads once the window closes", async () => {
  let t = 500;
  const cache = createDeskCache<number>({ maxAgeMs: 10, now: () => t });
  let reads = 0;
  const reader = async () => {
    reads += 1;
    return reads;
  };

  await cache.load("nav", reader);
  await cache.load("nav", reader);
  expect(reads).toBe(1);

  t += 11;
  expect(await cache.load("nav", reader)).toBe(2);
  expect(reads).toBe(2);
});
