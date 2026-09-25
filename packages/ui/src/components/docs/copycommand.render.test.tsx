import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { CopyCommand, type CopyCommandSample } from "./CopyCommand";

const SAMPLES: CopyCommandSample[] = [
  { label: "docker", protocol: "git clone", code: "git clone https://github.com/digithings-ai/digithings.git" },
  { label: "local", code: "make stack-local" },
];

describe("CopyCommand", () => {
  const html = renderToStaticMarkup(<CopyCommand samples={SAMPLES} />);

  it("renders one tab per sample, the first selected", () => {
    expect(html.match(/role="tab"/g)?.length).toBe(2);
    expect(html).toContain('aria-selected="true"');
    expect(html).toContain("docker");
    expect(html).toContain("local");
  });

  it("makes the command itself the copy button, not a sibling affordance", () => {
    expect(html).toContain('data-copied="false"');
    expect(html).toContain('aria-label="Copy docker command"');
    expect(html).toContain("https://github.com/digithings-ai/digithings.git");
  });

  it("splits the muted protocol prefix from the medium-weight payload", () => {
    expect(html).toContain('<span class="text-ink-mute">git clone</span>');
    expect(html).toContain('<span class="font-medium">');
  });

  it("uses only ink-family text colours — no syntax palette", () => {
    expect(html).not.toMatch(/text-(emerald|sky|amber|rose|violet|fuchsia|blue|green|red)-/);
  });

  it("treats a protocol that is not a prefix as plain payload", () => {
    const odd = renderToStaticMarkup(
      <CopyCommand samples={[{ label: "x", protocol: "nope", code: "make up" }]} />,
    );
    expect(odd).not.toContain('<span class="text-ink-mute">nope</span>');
    expect(odd).toContain('<span class="font-medium">make up</span>');
  });

  it("renders nothing for an empty sample set", () => {
    expect(renderToStaticMarkup(<CopyCommand samples={[]} />)).toBe("");
  });
});
