import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { DIGICHAT_SKIN_HOST_CONTRACT as contract } from "./thread-skin-host-contract";

const here = dirname(fileURLToPath(import.meta.url));
const read = (rel: string) => readFileSync(join(here, rel), "utf8");

/**
 * The skin host contract stays honest: every descriptor item must still be
 * implemented by the cited source file. If a host drops an accommodation,
 * this test — not a user screenshot — says so.
 */
describe("skin host contract matches the sources", () => {
  it("hosts set the scope marker per skin", () => {
    for (const file of contract.scopeMarker.setBy) {
      const src = read(`../../../../../../apps/digichat/${file}`);
      expect(src).toMatch(/data-thread-skin=\{/);
    }
  });

  it("the host stylesheet scans the kit", () => {
    const css = read(`../../../../../../apps/digichat/${contract.tailwindSources.hostStylesheet}`);
    expect(css).toContain(contract.tailwindSources.sourceDirective);
  });

  it("the host layout provides the Geist Mono variable", () => {
    const layout = read(`../../../../../../apps/digichat/${contract.fontVariables.hostLayout}`);
    expect(layout).toMatch(
      new RegExp(`variable:\\s*"${contract.fontVariables.variable}"`),
    );
  });

  it("the host client drives the theme dataset and classes", () => {
    const client = read(`../../../../../../apps/digichat/${contract.themeRoot.hostClient}`);
    expect(client).toContain(`dataset.${contract.themeRoot.dataset}`);
    for (const cls of contract.themeRoot.classes) {
      expect(client).toContain(`"${cls}"`);
    }
  });

  it("the host client mounts the prefs host", () => {
    const client = read(`../../../../../../apps/digichat/${contract.prefsHost.hostClient}`);
    expect(client).toContain(contract.prefsHost.hook);
  });

  it("the contract names the package stylesheets (WS1)", () => {
    expect(contract.stylesheets).toContain(
      "@digithings/ui/styles/digichat-app-theme.css",
    );
    expect(contract.stylesheets).toContain(
      "@digithings/ui/styles/chat-digichat.css",
    );
  });
});
