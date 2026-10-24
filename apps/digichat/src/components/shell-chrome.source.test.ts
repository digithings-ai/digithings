import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";

/**
 * Source contracts for the app shell chrome (epic #6327, slice U15).
 * Cheap, precise assertions for wiring that needs Auth.js + a transport to
 * render: the app shell's states, its skip path, and the absence of the
 * shadcn residue the audit logged.
 */

async function read(path: string): Promise<string> {
  return readFile(path, "utf8");
}

describe("app shell chrome", () => {
  it("mounts designed states instead of a bare loading line", async () => {
    const shell = await read("src/components/chat-shell.tsx");
    expect(shell).toContain("ChatShellLoading");
    expect(shell).toContain("ChatShellEmpty");
    expect(shell).toContain("ChatShellUnavailable");
    expect(shell).not.toContain("Loading…");
  });

  it("gives the main column a skip path", async () => {
    const shell = await read("src/components/chat-shell.tsx");
    expect(shell).toContain('href="#app-main"');
    expect(shell).toContain('id="app-main"');
    expect(shell).toContain("tabIndex={-1}");
  });

  it("collapses the rail for narrow viewports instead of squeezing the composer", async () => {
    const shell = await read("src/components/chat-shell.tsx");
    expect(shell).toMatch(/max-width:\s*48rem/);
    expect(shell).toContain("inert={collapsed");
  });

  it("keeps the shell chrome off muted-foreground and inline style resets", async () => {
    const shell = await read("src/components/chat-shell.tsx");
    expect(shell).not.toContain("text-muted-foreground");
    expect(shell).not.toMatch(/style=\{\{\s*background:\s*"transparent"/);
  });

  it("renders the send error as an alert, not body-coloured text", async () => {
    const panel = await read("src/components/chat-panel.tsx");
    expect(panel).toContain('role="alert"');
    expect(panel).not.toContain("text-destructive");
    expect(panel).not.toContain("shadow-lg");
    expect(panel).toContain("border-hair");
  });

  it("keeps the memory rail on the hairline system", async () => {
    const rail = await read("src/components/stock/memory-thread-list-sidebar.tsx");
    expect(rail).toContain("app-thread-rail");
    expect(rail).not.toMatch(/\brounded(-|\b)/);
    expect(rail).not.toContain("bg-muted");
    expect(rail).not.toContain("border-border");
    expect(rail).not.toMatch(/\buppercase\b/);
  });
});
