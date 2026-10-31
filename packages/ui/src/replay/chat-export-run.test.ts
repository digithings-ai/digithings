/**
 * @vitest-environment happy-dom
 */
import { afterEach, describe, expect, it, vi } from "vitest";

const saved = vi.hoisted(() => [] as Array<{ name: string; body: string; mime?: string }>);

vi.mock("../components/chat/transcript/save-file", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../components/chat/transcript/save-file")>()),
  saveTextFile: (name: string, body: string, mime?: string) => {
    saved.push({ name, body, mime });
  },
}));

import { chatExportStrings } from "../components/chat/transcript";
import { exportConversation, exportMessage } from "./chat-export-run";
import { exportFilename, snapshotFilename } from "./filename";
import { keepAnswerOnly, snapshotSource, transformSnapshotDom } from "./snapshot";

const NOW = "2026-10-30T18:20:00.000Z";
const messages = [
  { id: "u1", role: "user", content: [{ type: "text", text: "What moved overnight" }] },
  { id: "a1", role: "assistant", content: [{ type: "text", text: "Rates were flat." }] },
  { id: "u2", role: "user", content: [{ type: "text", text: "And the curve" }] },
  { id: "a2", role: "assistant", content: [{ type: "text", text: "It steepened." }] },
];

afterEach(() => {
  saved.length = 0;
  document.body.replaceChildren();
});

describe("exportFilename", () => {
  it("shares the snapshot name and swaps the extension", () => {
    expect(exportFilename("Desk", NOW, "And the curve", "md")).toBe(
      "desk-2026-10-30-1820-and-the-curve.md",
    );
    expect(snapshotFilename("Desk", NOW, "And the curve")).toBe(
      "desk-2026-10-30-1820-and-the-curve.html",
    );
  });
});

describe("exportConversation markdown", () => {
  it("saves every turn with User / Assistant headings", async () => {
    await exportConversation({ format: "md", messages, doc: document, now: NOW });
    expect(saved).toHaveLength(1);
    expect(saved[0]!.name).toMatch(/-2026-10-30-1820-and-the-curve\.md$/);
    expect(saved[0]!.body).toBe(
      [
        "## User\n\nWhat moved overnight",
        "## Assistant\n\nRates were flat.",
        "## User\n\nAnd the curve",
        "## Assistant\n\nIt steepened.",
      ].join("\n\n---\n\n"),
    );
  });

  it("localizes the headings", async () => {
    await exportConversation({
      format: "md",
      messages,
      strings: chatExportStrings("fr"),
      doc: document,
      now: NOW,
    });
    expect(saved[0]!.body.startsWith("## Utilisateur")).toBe(true);
  });

  it("saves nothing for an empty thread", async () => {
    await exportConversation({ format: "md", messages: [], doc: document, now: NOW });
    expect(saved).toHaveLength(0);
  });
});

describe("exportMessage markdown", () => {
  it("saves only that answer, named after its own question", async () => {
    await exportMessage({
      format: "md",
      message: messages[1],
      messageId: "a1",
      messages,
      trigger: null,
      doc: document,
      now: NOW,
    });
    expect(saved).toHaveLength(1);
    expect(saved[0]!.name).toMatch(/-what-moved-overnight\.md$/);
    expect(saved[0]!.body).toBe("Rates were flat.");
  });
});

describe("keepAnswerOnly", () => {
  it("drops user turns and keeps the assistant one", () => {
    const root = document.createElement("div");
    root.innerHTML =
      '<div data-role="user">Q</div><div data-role="assistant" data-message-id="a1">A</div>';
    keepAnswerOnly(root);
    expect(root.querySelector("[data-role='user']")).toBeNull();
    expect(root.textContent).toBe("A");
  });

  it("drops reasoning and tool output from the answer, like the markdown export", () => {
    const root = document.createElement("div");
    root.innerHTML = `
      <div data-role="assistant" data-message-id="a1">
        <div data-slot="aui_chain-of-thought"><div data-slot="aui_work-chain">chain-token</div></div>
        <div data-slot="reasoning-root"><div class="aui-md">reasoning-token</div></div>
        <div data-slot="tool-group-root"><div data-slot="tool-fallback-root">group-tool-token</div></div>
        <div data-slot="tool-fallback-root"><pre data-slot="tool-fallback-result">tool-result-token</pre></div>
        <div data-slot="aui_private-work-step">private-step-token</div>
        <div data-export-work="">custom-work-token</div>
        <div class="aui-md"><p>answer-token</p></div>
      </div>`;
    keepAnswerOnly(root);
    expect(root.textContent?.trim()).toBe("answer-token");
  });
});

describe("HTML snapshot of a clone skin", () => {
  it("finds a [data-export-thread] root and drops the [data-export-chrome] parts", () => {
    document.body.innerHTML = `
      <div data-export-thread="">
        <div data-role="user" data-message-id="u1">What moved</div>
        <div data-role="assistant" data-message-id="a1">
          <div class="aui-code-header-root"><span>ts</span><button>Copy</button></div>
          Rates were flat.
          <div data-export-chrome=""><button>More</button></div>
        </div>
        <form data-export-chrome=""><textarea></textarea></form>
        <div class="aui-overlay-scroll" aria-hidden="true"><div class="aui-overlay-thumb"></div></div>
      </div>`;
    const shell = snapshotSource(document);
    expect(shell).toBeTruthy();
    transformSnapshotDom(shell!);
    const html = shell!.outerHTML;
    expect(html).toContain("What moved");
    expect(html).toContain("Rates were flat.");
    expect(html).not.toContain("textarea");
    expect(html).not.toContain("More");
    expect(html).not.toContain("Copy");
    expect(html).not.toContain("aui-overlay-scroll");
  });
});
