// @vitest-environment happy-dom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ByokCliFlow } from "./byok-cli-flow";

describe("ByokCliFlow", () => {
  beforeEach(() => {
    document.cookie = "digichat_byok_pref=; max-age=0";
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("walks provider -> key -> model -> activate for an OpenAI key", async () => {
    // The component fires a fetch on mount too (the openrouter live-catalog
    // prefetch — provider defaults to "openrouter" before any click), so the
    // mock must hand back a fresh Response per call: a single cached Response
    // instance can only have its body read once, and reusing it here would
    // make the *second* call (the actual key ping) fail with a body-already-
    // read error instead of exercising the activation path under test.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify({ ok: true, model: "gpt-4o-mini" }), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        ),
      ),
    );
    const onActivate = vi.fn();
    render(<ByokCliFlow onClose={() => {}} onActivate={onActivate} />);

    fireEvent.click(screen.getByText("openai"));
    const keyInput = screen.getByLabelText("Paste API key, then Enter");
    fireEvent.change(keyInput, { target: { value: "sk-test-1234" } });
    fireEvent.keyDown(keyInput, { key: "Enter" });

    const defaultOption = await screen.findByText("(provider default)");
    fireEvent.click(defaultOption);

    await waitFor(() => expect(onActivate).toHaveBeenCalledWith("sk-test-1234", "openai", ""));
    expect(await screen.findByText(/ok — BYOK active for this session/)).toBeInTheDocument();
  });

  it("shows an inline error and does not activate on an invalid key format", async () => {
    // Stub fetch even though this test never inspects a response: provider
    // defaults to "openrouter" on mount, so the live-catalog prefetch effect
    // fires regardless — without a stub it would hit the real network.
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.reject(new Error("no network in tests"))));
    render(<ByokCliFlow onClose={() => {}} onActivate={() => {}} />);
    fireEvent.click(screen.getByText("openai"));
    const keyInput = screen.getByLabelText("Paste API key, then Enter");
    fireEvent.change(keyInput, { target: { value: "not-a-key" } });
    fireEvent.keyDown(keyInput, { key: "Enter" });
    expect(await screen.findByText(/must start with sk-/)).toBeInTheDocument();
  });

  it("refuses activation when the ping fails, and stays on the model step for retry", async () => {
    // Fresh Response per call — see the note in the first test above.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify({ ok: false, error: "Incorrect API key" }), {
            status: 400,
            headers: { "content-type": "application/json" },
          }),
        ),
      ),
    );
    const onActivate = vi.fn();
    render(<ByokCliFlow onClose={() => {}} onActivate={onActivate} />);
    fireEvent.click(screen.getByText("openai"));
    const keyInput = screen.getByLabelText("Paste API key, then Enter");
    fireEvent.change(keyInput, { target: { value: "sk-bad" } });
    fireEvent.keyDown(keyInput, { key: "Enter" });
    fireEvent.click(await screen.findByText("(provider default)"));
    expect(await screen.findByText("Incorrect API key")).toBeInTheDocument();
    expect(onActivate).not.toHaveBeenCalled();
    expect(screen.getByText("(provider default)")).toBeInTheDocument(); // still on model step
  });

  it("shows OpenRouter tier tabs once the live catalog fetch resolves", async () => {
    // Fresh Response per call — see the note in the first test above.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              ok: true,
              free: [{ id: "openai/gpt-oss-20b:free", label: "gpt-oss-20b:free", supportsTools: false }],
              opensource: [],
              flagship: [],
              all: [{ id: "openai/gpt-oss-20b:free", label: "gpt-oss-20b:free", supportsTools: false }],
            }),
            { status: 200, headers: { "content-type": "application/json" } },
          ),
        ),
      ),
    );
    render(<ByokCliFlow onClose={() => {}} onActivate={() => {}} />);
    // openrouter is already the default provider state, so the live-catalog
    // prefetch effect fires on mount regardless of this click — the click is
    // what advances the stepper from "provider" to "key" so we can submit a
    // valid OpenRouter-format key and reach the "model" step, which is where
    // the tier tabs actually render.
    fireEvent.click(screen.getByText("openrouter"));
    const keyInput = screen.getByLabelText("Paste API key, then Enter");
    fireEvent.change(keyInput, { target: { value: "sk-or-v1-test" } });
    fireEvent.keyDown(keyInput, { key: "Enter" });
    await waitFor(() => expect(screen.getByText(/free \(1\)/)).toBeInTheDocument());
  });
});
