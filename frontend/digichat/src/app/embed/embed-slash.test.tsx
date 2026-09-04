// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DigiChatSession } from "@digithings/digichat-ui";

const embedClientSrc = readFileSync(
  path.join(path.dirname(fileURLToPath(import.meta.url)), "embed-client.tsx"),
  "utf8",
);

describe("public /embed slash surface (#3418)", () => {
  it("drops the top-right LanguageSelect once /lang is wired", () => {
    expect(embedClientSrc).not.toMatch(/LanguageSelect/);
    expect(embedClientSrc).toMatch(/onLanguageChange=\{setLanguage\}/);
    expect(embedClientSrc).toMatch(/forceTool/);
    expect(embedClientSrc).toMatch(/reset: chat\.reset/);
  });

  it("lists public search and Vault copy without private names", async () => {
    const user = userEvent.setup();
    render(
      <DigiChatSession
        welcomeIntro=""
        placeholder="ask digichat…"
        showByok={false}
        showIntro={false}
        webSearchAllowed
        chat={{ messages: [], busy: false, error: null, send: () => {} }}
      />,
    );
    await user.type(screen.getByRole("textbox"), "/");
    expect(screen.getByText("Search the knowledge base")).toBeTruthy();
    expect(screen.getByText("Vault")).toBeTruthy();
    expect(screen.getByText("Web search")).toBeTruthy();
    expect(screen.getByText("Settings")).toBeTruthy();
    expect(screen.queryByText(/digisearch/i)).toBeNull();
    expect(screen.queryByText(/datatap/i)).toBeNull();
  });

  it("navigates the palette with ArrowUp/Down and Enter (#3556)", async () => {
    const user = userEvent.setup();
    const send = vi.fn();
    render(
      <DigiChatSession
        welcomeIntro=""
        placeholder="ask digichat…"
        showByok={false}
        showIntro={false}
        chat={{ messages: [], busy: false, error: null, send }}
      />,
    );
    const box = screen.getByRole("textbox");
    await user.type(box, "/");
    await user.keyboard("{ArrowDown}");
    await user.keyboard("{Enter}");
    expect((box as HTMLTextAreaElement).value).toBe("/vault ");
    expect(send).not.toHaveBeenCalled();
  });

  it("dives into language presets with Up/Down — no free typing (#3556)", async () => {
    const user = userEvent.setup();
    const onLanguageChange = vi.fn();
    render(
      <DigiChatSession
        welcomeIntro=""
        placeholder="ask digichat…"
        showByok={false}
        showIntro={false}
        onLanguageChange={onLanguageChange}
        chat={{ messages: [], busy: false, error: null, send: () => {} }}
      />,
    );
    const box = screen.getByRole("textbox");
    await user.type(box, "/lang");
    await user.keyboard("{Enter}");
    expect(screen.getByText("German")).toBeTruthy();
    await user.keyboard("{ArrowDown}");
    await user.keyboard("{Enter}");
    expect(onLanguageChange).toHaveBeenCalledWith("de");
  });

  it("/websearch toggles when allowed and refuses when not (#3556)", async () => {
    const user = userEvent.setup();
    const onWebSearchToggle = vi.fn();
    const { rerender } = render(
      <DigiChatSession
        welcomeIntro=""
        placeholder="ask digichat…"
        showByok={false}
        showIntro={false}
        webSearchAllowed
        webSearchEnabled={false}
        onWebSearchToggle={onWebSearchToggle}
        chat={{ messages: [], busy: false, error: null, send: () => {} }}
      />,
    );
    await user.type(screen.getByRole("textbox"), "/websearch");
    await user.keyboard("{Enter}");
    expect(onWebSearchToggle).toHaveBeenCalled();
    expect(screen.getByText(/Web search on/i)).toBeTruthy();

    rerender(
      <DigiChatSession
        welcomeIntro=""
        placeholder="ask digichat…"
        showByok={false}
        showIntro={false}
        webSearchAllowed={false}
        chat={{ messages: [], busy: false, error: null, send: () => {} }}
      />,
    );
    await user.type(screen.getByRole("textbox"), "/websearch");
    await user.keyboard("{Enter}");
    expect(screen.getByText(/not enabled for this tenant/i)).toBeTruthy();
  });

  it("/byok opens settings and /settings opens the CLI panel (#3556)", async () => {
    const user = userEvent.setup();
    const openSettings = vi.fn();
    render(
      <DigiChatSession
        welcomeIntro=""
        placeholder="ask digichat…"
        showByok
        showIntro={false}
        chat={{
          messages: [],
          busy: false,
          error: null,
          send: () => {},
          openSettings,
        }}
      />,
    );
    await user.type(screen.getByRole("textbox"), "/byok");
    await user.keyboard("{Enter}");
    expect(openSettings).toHaveBeenCalled();

    await user.type(screen.getByRole("textbox"), "/settings");
    await user.keyboard("{Enter}");
    expect(screen.getByRole("dialog", { name: "Settings" })).toBeTruthy();
  });

  it("/lang switches language client-side and does not send", async () => {
    const user = userEvent.setup();
    const send = vi.fn();
    const onLanguageChange = vi.fn();
    render(
      <DigiChatSession
        welcomeIntro=""
        placeholder="ask digichat…"
        showByok={false}
        showIntro={false}
        onLanguageChange={onLanguageChange}
        chat={{ messages: [], busy: false, error: null, send }}
      />,
    );
    await user.type(screen.getByRole("textbox"), "/lang de");
    await user.keyboard("{Enter}");
    expect(onLanguageChange).toHaveBeenCalledWith("de");
    expect(send).not.toHaveBeenCalled();
    expect(screen.getByText(/Language set to German/i)).toBeTruthy();
  });

  it("/search sends the user string as the tool argument with no model hint", async () => {
    const user = userEvent.setup();
    const send = vi.fn();
    render(
      <DigiChatSession
        welcomeIntro=""
        placeholder="ask digichat…"
        showByok={false}
        showIntro={false}
        chat={{ messages: [], busy: false, error: null, send }}
      />,
    );
    await user.type(screen.getByRole("textbox"), "/search RS256 token exchange");
    await user.keyboard("{Enter}");
    expect(send).toHaveBeenCalledWith("RS256 token exchange", { forceTool: "digisearch" });
    const [arg] = send.mock.calls[0];
    expect(arg).not.toMatch(/please/i);
  });

  it("empty /search waits instead of sending", async () => {
    const user = userEvent.setup();
    const send = vi.fn();
    render(
      <DigiChatSession
        welcomeIntro=""
        placeholder="ask digichat…"
        showByok={false}
        showIntro={false}
        chat={{ messages: [], busy: false, error: null, send }}
      />,
    );
    await user.type(screen.getByRole("textbox"), "/search");
    await user.keyboard("{Enter}");
    expect(send).not.toHaveBeenCalled();
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("/search ");
  });

  it("/new clears the transcript via reset", async () => {
    const user = userEvent.setup();
    const reset = vi.fn();
    render(
      <DigiChatSession
        welcomeIntro=""
        placeholder="ask digichat…"
        showByok={false}
        showIntro={false}
        chat={{
          messages: [{ role: "user", content: "hello" }],
          busy: false,
          error: null,
          send: () => {},
          reset,
        }}
      />,
    );
    expect(screen.getByText("hello")).toBeTruthy();
    await user.type(screen.getByRole("textbox"), "/new");
    await user.keyboard("{Enter}");
    expect(reset).toHaveBeenCalled();
  });
});
