import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MotionProvider } from "../../motion/primitives";
import { ChatPlayback, type ChatPlaybackStep } from "./ChatPlayback";

const SCRIPT: ChatPlaybackStep[] = [
  { role: "user", text: "List the sample items" },
  {
    role: "tool",
    tool: { name: "sample.list", args: "limit=2", result: { columns: ["id", "name"], rows: [["ab", "cd"]] }, masked: true },
  },
  { role: "tool", tool: { name: "sample.plain", args: "x=1", result: "hello world" } },
  { role: "assistant", text: "Two items came back." },
];

function render() {
  return renderToStaticMarkup(
    <MotionProvider>
      <ChatPlayback script={SCRIPT} header="sample session" badge="Simulation · scripted · not connected" />
    </MotionProvider>,
  );
}

describe("ChatPlayback (server / no-JS / reduced motion)", () => {
  it("renders the full transcript statically, in order", () => {
    const html = render();
    expect(html).toContain('data-mode="static"');
    expect(html).toContain("List the sample items");
    expect(html).toContain("sample.list");
    expect(html).toContain("limit=2");
    expect(html).toContain("Two items came back.");
    expect(html.indexOf("List the sample items")).toBeLessThan(html.indexOf("sample.list"));
    expect(html.indexOf("sample.list")).toBeLessThan(html.indexOf("Two items came back."));
  });

  it("puts the required badge and header in the frame chrome", () => {
    const html = render();
    expect(html).toContain("Simulation · scripted · not connected");
    expect(html).toContain("sample session");
    expect(html).toContain('data-slot="chat-playback-badge"');
  });

  it("masks results when asked and shows plain ones otherwise", () => {
    const html = render();
    expect(html).toContain("▒▒");
    expect(html).not.toContain(">cd<");
    expect(html).toContain("hello world");
  });

  it("is aria-live off, hides the animated copy and carries an sr-only transcript", () => {
    const html = render();
    expect(html).toContain('aria-live="off"');
    expect(html).toContain('aria-hidden="true"');
    expect(html).toContain('aria-label="Full transcript"');
    expect(html).toContain("You: List the sample items");
    expect(html).toContain("The result is withheld in this simulation.");
    expect(html).toContain("Result: hello world");
  });

  it("shows no controls and no invented durations with no JS", () => {
    const html = render();
    expect(html).not.toContain("[pause]");
    expect(html).not.toContain("[replay]");
    expect(html).not.toMatch(/\d+ms/);
  });

  it("uses tokens only", () => {
    const html = render();
    expect(html).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(html).not.toMatch(/rgba?\(/);
  });
});
