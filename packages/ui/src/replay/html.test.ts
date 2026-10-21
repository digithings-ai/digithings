/**
 * @vitest-environment happy-dom
 */
import { Window } from "happy-dom";
import { describe, expect, it } from "vitest";
import { loadReplayStyles } from "./assets";
import { fixtureDocument } from "./fixture";
import { messagesToReplay } from "./from-messages";
import { buildReplayHtml, replayDownloadName } from "./html";

const JWT =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U";

function boot(html: string): Window {
  const win = new Window({ url: "https://replay.local/northwind.html" });
  const script = html.match(/<script>([\s\S]*)<\/script\s*>/i)?.[1] ?? "";
  win.document.write(html.replace(/<script>[\s\S]*<\/script\s*>/i, ""));
  win.document.close();
  win.eval(script);
  return win;
}

describe("buildReplayHtml", () => {
  const doc = fixtureDocument();
  const html = buildReplayHtml(doc, "/* test */");

  it("names the file from the deployment and the UTC day", () => {
    expect(replayDownloadName(doc)).toBe("northwind-2026-10-21.html");
  });

  it("renders the live thread hooks, suggestions, and an inline stylesheet", () => {
    expect(html).toContain('data-thread-skin="digichat"');
    expect(html).toContain('data-slot="aui_user-message-root"');
    expect(html).toContain("aui-user-message-content");
    expect(html).toContain("aui-md");
    expect(html).toContain("Copper hedge was lifted");
    expect(html).toContain("arguments");
    expect(html).toContain("result");
    expect(html).toContain("What moved in the book?");
    expect(html).toContain("research corpus");
    expect(html).toContain("<style>");
    expect(html).not.toMatch(/<link[^>]+stylesheet/i);
    expect(html).toContain('id="replay-play"');
    expect(html).toContain("Default dark");
    expect(html).toContain("Default light");
    expect(html).not.toContain("</script><");
  });

  it("keeps tool cards expandable and steps turns from the keyboard", () => {
    const win = boot(html);
    const details = win.document.querySelector("[data-slot='tool-fallback-root']");
    expect(details).toBeTruthy();
    if (!(details instanceof win.HTMLDetailsElement)) throw new Error("expected details");
    details.open = true;
    expect(details.open).toBe(true);
    expect(details.textContent).toContain("overnight book changes");
    expect(details.textContent).toContain("Copper hedge was lifted");

    const root = win.document.getElementById("replay");
    expect(root?.getAttribute("data-revealed")).toBe("2");
    win.dispatchEvent(new win.KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));
    expect(root?.getAttribute("data-revealed")).toBe("1");
    expect(root?.getAttribute("data-mode")).toBe("paused");
    win.dispatchEvent(new win.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    expect(root?.getAttribute("data-revealed")).toBe("2");

    const theme = win.document.getElementById("replay-theme");
    if (!(theme instanceof win.HTMLSelectElement)) throw new Error("expected theme select");
    theme.value = "default|light";
    theme.dispatchEvent(new win.Event("change", { bubbles: true }));
    expect(win.document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(win.document.documentElement.hasAttribute("data-palette")).toBe(false);

    const view = win.document.getElementById("replay-view");
    if (!(view instanceof win.HTMLSelectElement)) throw new Error("expected view select");
    view.value = "verbose";
    view.dispatchEvent(new win.Event("change", { bubbles: true }));
    expect(root?.getAttribute("data-view")).toBe("verbose");
    expect((details as { open: boolean }).open).toBe(true);
    win.close();
  });

  it("never writes tokens into the file, including beside inlined fonts", () => {
    const poisoned = messagesToReplay(
      [
        {
          id: "u",
          role: "user",
          parts: [
            {
              type: "text",
              text: "dgk_live_TESTSECRET99 https://desk.example/cb?api_key=query-plain-9f3c2a",
            },
          ],
        },
        {
          id: "a",
          role: "assistant",
          parts: [
            {
              type: "reasoning",
              text: `Authorization: Bearer ${JWT}`,
            },
            {
              type: "tool-digisearch",
              state: "output-available",
              input: { "X-Embed-Token": "embed-plain-9f3c2a" },
              output: { api_key: "sk-ant-TESTSECRET99", inviteKey: "invite-plain-9f3c2a" },
            },
            { type: "text", text: "digi_live_TESTSECRET99" },
          ],
        },
      ],
      {
        deployment: "acme",
        title: "Acme",
        theme: { preference: "dark", resolved: "dark", palette: "default", view: "balanced" },
      },
      "2026-10-21T00:00:00.000Z",
    );
    const file = buildReplayHtml(poisoned, loadReplayStyles());
    for (const secret of [
      "dgk_live_TESTSECRET99",
      "digi_live_TESTSECRET99",
      "sk-ant-TESTSECRET99",
      "invite-plain-9f3c2a",
      "embed-plain-9f3c2a",
      "query-plain-9f3c2a",
      JWT,
    ]) {
      expect(file).not.toContain(secret);
    }
    expect(file).toContain("[redacted]");
    expect(file).toContain("@font-face");
    expect(file).toContain("font/woff2");
    expect(file).not.toMatch(/https?:\/\/[^"'\s]+woff2/);
  });
});
