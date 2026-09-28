import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Node, not jsdom. The component tests here assert on server-rendered
    // markup (react-dom/server) rather than driving a DOM — which is also the
    // honest thing to assert for this package: the digichat embed must read
    // without client JS, so every activity row has to be in the first paint.
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
