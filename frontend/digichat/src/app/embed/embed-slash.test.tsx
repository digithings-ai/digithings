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

  it("lists public search and docs copy without private names", async () => {
    const user = userEvent.setup();
    render(
      <DigiChatSession
        welcomeIntro=""
        placeholder="ask digichat…"
        showByok={false}
        showIntro={false}
        chat={{ messages: [], busy: false, error: null, send: () => {} }}
      />,
    );
    await user.type(screen.getByRole("textbox"), "/");
    expect(screen.getByText("Search the knowledge base")).toBeTruthy();
    expect(screen.getByText("Find original documents")).toBeTruthy();
    expect(screen.queryByText(/digisearch/i)).toBeNull();
    expect(screen.queryByText(/datatap/i)).toBeNull();
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
