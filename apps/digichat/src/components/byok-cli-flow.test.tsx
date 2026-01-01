// @vitest-environment happy-dom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ByokCliFlow } from "./byok-cli-flow";
import { useBYOKKey } from "@/hooks/use-byok-key";

describe("ByokCliFlow", () => {
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

  // #4994 — /api/byok/models now answers every BYOK provider, not just
  // openrouter. x.ai is the cleanest probe: it has no key-step ping and no
  // live fetch of its own, so the model list can only have come from the
  // catalog branch of the route.
  it("populates the model picker from the catalog for a provider with no live list", async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      if (String(url).includes("/api/byok/models")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ok: true,
              provider: "xai",
              source: "catalog",
              fetchedAt: "2026-10-02T23:38:18+00:00",
              free: [],
              opensource: [],
              flagship: [{ id: "grok-4.5", label: "Grok 4.5" }],
              all: [
                { id: "grok-4.5", label: "Grok 4.5" },
                { id: "grok-4.3", label: "Grok 4.3" },
              ],
            }),
            { status: 200, headers: { "content-type": "application/json" } },
          ),
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify({ ok: false, error: "Incorrect API key" }), {
          status: 400,
          headers: { "content-type": "application/json" },
        }),
      );
    });
    vi.stubGlobal("fetch", fetchSpy);
    render(<ByokCliFlow onClose={() => {}} onActivate={() => {}} />);

    fireEvent.click(screen.getByText("xai"));
    const keyInput = screen.getByLabelText("Paste API key, then Enter");
    fireEvent.change(keyInput, { target: { value: "xai-test" } });
    fireEvent.keyDown(keyInput, { key: "Enter" });

    // Labels come from the catalog, so this asserts the payload reached the
    // picker rather than the bare ids falling back to themselves.
    expect(await screen.findByText("Grok 4.5")).toBeInTheDocument();
    expect(screen.getByText("Grok 4.3")).toBeInTheDocument();
    const modelCalls = fetchSpy.mock.calls.filter(([u]) => String(u).includes("/api/byok/models"));
    expect(modelCalls.some(([u]) => String(u).includes("provider=xai"))).toBe(true);
  });

  // #4994 review finding 1 — openai is the only BYOK provider with
  // requiresModel: false, so its picker is the only one that offers the ""
  // ("(provider default)") sentinel. Every other branch of modelOptions
  // guards on byokRequiresModel before prepending it; the catalog branch did
  // not, so as soon as a catalog list loaded for openai the sentinel vanished
  // and the one option that works without naming a model became unselectable.
  // The ping here returns no `models` array so the catalog branch is the only
  // tiered list in play (a real openai catalog equals its presets today, so
  // the branch is unreachable without a mocked payload — this is the guard for
  // the day litellm.yaml grows a routable openai model outside the presets).
  it("keeps (provider default) for openai once the catalog list loads", async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      if (String(url).includes("/api/byok/models")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ok: true,
              provider: "openai",
              source: "catalog",
              free: [],
              opensource: [],
              flagship: [{ id: "gpt-5.4", label: "GPT-5.4" }],
              all: [{ id: "gpt-5.4", label: "GPT-5.4" }],
            }),
            { status: 200, headers: { "content-type": "application/json" } },
          ),
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify({ ok: true, model: "gpt-4o-mini" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    });
    vi.stubGlobal("fetch", fetchSpy);
    render(<ByokCliFlow onClose={() => {}} onActivate={() => {}} />);

    fireEvent.click(screen.getByText("openai"));
    const keyInput = screen.getByLabelText("Paste API key, then Enter");
    fireEvent.change(keyInput, { target: { value: "sk-test-1234" } });
    fireEvent.keyDown(keyInput, { key: "Enter" });

    // The catalog entry is what proves the catalog branch won.
    expect(await screen.findByText("GPT-5.4")).toBeInTheDocument();
    expect(screen.getByText("(provider default)")).toBeInTheDocument();
  });

  // #4994 — catalog membership is not key-scoped availability. The key-step
  // ping returns exactly what this key may call, so it must stay above the
  // catalog in modelOptions' precedence; otherwise a user whose key can see
  // two models is offered twenty-six they cannot call.
  it("keeps the key-scoped ping list above the catalog list", async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      if (String(url).includes("/api/byok/models")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ok: true,
              provider: "openai",
              source: "catalog",
              free: [],
              opensource: [],
              flagship: [{ id: "gpt-5.4", label: "GPT-5.4" }],
              all: [
                { id: "gpt-5.4", label: "GPT-5.4" },
                { id: "gpt-4o-mini", label: "GPT-4o mini" },
                { id: "gpt-4o", label: "GPT-4o" },
              ],
            }),
            { status: 200, headers: { "content-type": "application/json" } },
          ),
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({
            ok: true,
            model: "gpt-4o-mini",
            models: [
              { id: "gpt-4o-mini", label: "gpt-4o-mini" },
              { id: "gpt-4o", label: "gpt-4o" },
            ],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
    });
    vi.stubGlobal("fetch", fetchSpy);
    render(<ByokCliFlow onClose={() => {}} onActivate={() => {}} />);

    fireEvent.click(screen.getByText("openai"));
    const keyInput = screen.getByLabelText("Paste API key, then Enter");
    fireEvent.change(keyInput, { target: { value: "sk-test-1234" } });
    fireEvent.keyDown(keyInput, { key: "Enter" });

    expect(await screen.findByText("gpt-4o")).toBeInTheDocument();
    // The catalog's flagship entry is in `all` but the ping won, so neither
    // its id nor its catalog label may reach the picker.
    expect(screen.queryByText("GPT-5.4")).not.toBeInTheDocument();
    expect(screen.queryByText("gpt-5.4")).not.toBeInTheDocument();
  });

  // #4994 — `if (tieredOptions)` used to be truthy even when every bucket was
  // empty, so selecting an empty tier collapsed the picker to just "custom…"
  // instead of falling through to the presets.
  it("falls back to presets when the selected catalog tier is empty", async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      if (String(url).includes("/api/byok/models")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ok: true,
              provider: "anthropic",
              source: "catalog",
              free: [],
              opensource: [],
              flagship: [],
              all: [{ id: "claude-opus-4-5", label: "Claude Opus 4.5" }],
            }),
            { status: 200, headers: { "content-type": "application/json" } },
          ),
        );
      }
      // A ping with no `models` array: key-scoped list is unavailable, so the
      // catalog owns the picker — which is exactly the state under test.
      return Promise.resolve(
        new Response(JSON.stringify({ ok: true, model: "claude-opus-4-5" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    });
    vi.stubGlobal("fetch", fetchSpy);
    render(<ByokCliFlow onClose={() => {}} onActivate={() => {}} />);

    fireEvent.click(screen.getByText("anthropic"));
    const keyInput = screen.getByLabelText("Paste API key, then Enter");
    fireEvent.change(keyInput, { target: { value: "sk-ant-test" } });
    fireEvent.keyDown(keyInput, { key: "Enter" });

    // Default tier "all" has one member, so the catalog list renders.
    expect(await screen.findByText("Claude Opus 4.5")).toBeInTheDocument();

    // Now select the empty "free" tier — the presets must come back rather
    // than the picker emptying out to just "custom…".
    fireEvent.click(await screen.findByText(/free \(0\)/));
    expect(await screen.findByText("claude-sonnet-4-6")).toBeInTheDocument();
    // haiku is a preset that the mocked catalog does NOT carry, so seeing it
    // proves the fall-through reached byokModelPresets. #5000 made the preset
    // ids and the catalog ids overlap (both are now claude-*-4-5/4-6), so an
    // opus option can no longer be used to tell the two sources apart — and
    // modelLabels resolves it to the catalog's friendlier "Claude Opus 4.5"
    // rather than the bare id, which is accurate: same id, same model.
    expect(await screen.findByText("claude-haiku-4-5")).toBeInTheDocument();
  });

  it("pings at the key step for OpenAI and populates the model picker from the live list", async () => {
    // Two distinct response shapes needed: the openrouter live-catalog
    // prefetch fires on mount (provider defaults to "openrouter" before any
    // click) and must not be confused with the byok/test key-step ping.
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      if (String(url).includes("/api/byok/models")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ ok: true, free: [], opensource: [], flagship: [], all: [] }),
            { status: 200, headers: { "content-type": "application/json" } },
          ),
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({
            ok: true,
            model: "gpt-4o-mini",
            models: [
              { id: "gpt-4o-mini", label: "gpt-4o-mini" },
              { id: "gpt-4o", label: "gpt-4o" },
            ],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
    });
    vi.stubGlobal("fetch", fetchSpy);
    render(<ByokCliFlow onClose={() => {}} onActivate={() => {}} />);

    fireEvent.click(screen.getByText("openai"));
    const keyInput = screen.getByLabelText("Paste API key, then Enter");
    fireEvent.change(keyInput, { target: { value: "sk-test-1234" } });
    fireEvent.keyDown(keyInput, { key: "Enter" });

    // The ping fires as soon as the key step advances — not after a model
    // is picked. Three total fetch calls since #4994: the openrouter
    // mount-time catalog prefetch, the openai catalog prefetch when the
    // provider changes, then this key-step ping.
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(3));
    const testCalls = fetchSpy.mock.calls.filter(([u]) => String(u).includes("/api/byok/test"));
    expect(testCalls).toHaveLength(1);
    expect(String(testCalls[0][0])).toContain("/api/byok/test");
    expect(await screen.findByText("gpt-4o")).toBeInTheDocument();
    expect(screen.getByText("gpt-4o-mini")).toBeInTheDocument();
  });

  // Regression: modelOptions used to check liveKeyStepModels before the
  // !byokRequiresModel(provider) branch that prepends "" ("(provider
  // default)"). OpenAI is the only key-step-ping provider with
  // byokRequiresModel === false, so once its ping resolved with a real
  // models list, "(provider default)" silently disappeared for the rest of
  // the session. See #2347 final whole-branch review.
  it("keeps the (provider default) option for OpenAI once the live key-step ping resolves", async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      if (String(url).includes("/api/byok/models")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ ok: true, free: [], opensource: [], flagship: [], all: [] }),
            { status: 200, headers: { "content-type": "application/json" } },
          ),
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({
            ok: true,
            model: "gpt-4o-mini",
            models: [
              { id: "gpt-4o-mini", label: "gpt-4o-mini" },
              { id: "gpt-4o", label: "gpt-4o" },
            ],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
    });
    vi.stubGlobal("fetch", fetchSpy);
    render(<ByokCliFlow onClose={() => {}} onActivate={() => {}} />);

    fireEvent.click(screen.getByText("openai"));
    const keyInput = screen.getByLabelText("Paste API key, then Enter");
    fireEvent.change(keyInput, { target: { value: "sk-test-1234" } });
    fireEvent.keyDown(keyInput, { key: "Enter" });

    expect(await screen.findByText("gpt-4o")).toBeInTheDocument();
    expect(screen.getByText("(provider default)")).toBeInTheDocument();
  });

  it("falls back to preset models when the key-step ping fails for Anthropic, without a user-visible error", async () => {
    const fetchSpy = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ ok: false, error: "Incorrect API key" }), {
          status: 400,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchSpy);
    render(<ByokCliFlow onClose={() => {}} onActivate={() => {}} />);

    fireEvent.click(screen.getByText("anthropic"));
    const keyInput = screen.getByLabelText("Paste API key, then Enter");
    fireEvent.change(keyInput, { target: { value: "sk-ant-test" } });
    fireEvent.keyDown(keyInput, { key: "Enter" });

    expect(await screen.findByText("claude-sonnet-4-6")).toBeInTheDocument();
    expect(screen.queryByText("Incorrect API key")).not.toBeInTheDocument();
  });

  it.each([
    ["openai", "sk-test-1234", "gpt-4o"],
    ["anthropic", "sk-ant-test", "claude-3-5-haiku-20241022"],
    ["gemini", "AIzaTest", "gemini-2.0-flash"],
  ] as const)(
    "completes %s with exactly one /api/byok/test call, reusing the key-step ping at activation",
    async (providerName, key, model) => {
      const fetchSpy = vi.fn().mockImplementation((url: string) => {
        if (String(url).includes("/api/byok/models")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ ok: true, free: [], opensource: [], flagship: [], all: [] }),
              { status: 200, headers: { "content-type": "application/json" } },
            ),
          );
        }
        return Promise.resolve(
          new Response(JSON.stringify({ ok: true, model, models: [{ id: model, label: model }] }), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        );
      });
      vi.stubGlobal("fetch", fetchSpy);
      const onActivate = vi.fn();
      render(<ByokCliFlow onClose={() => {}} onActivate={onActivate} />);

      fireEvent.click(screen.getByText(providerName));
      const keyInput = screen.getByLabelText("Paste API key, then Enter");
      fireEvent.change(keyInput, { target: { value: key } });
      fireEvent.keyDown(keyInput, { key: "Enter" });

      // Wait for the key-step ping to resolve (the live model appears)
      // before clicking — this is what makes reuse-at-activation
      // deterministic instead of racing a fast human click against the
      // in-flight prefetch.
      const modelOption = await screen.findByText(model);
      fireEvent.click(modelOption);

      await waitFor(() => expect(onActivate).toHaveBeenCalledWith(key, providerName, model));
      const testCalls = fetchSpy.mock.calls.filter(([u]) => String(u).includes("/api/byok/test"));
      expect(testCalls).toHaveLength(1);
    },
  );
});

// Regression for the final-review Important finding: the digichat_byok_pref
// cookie restored a {provider, model} preference but every consumer only ever
// passed it into `active`, which is gated behind isSet — never true from a
// cookie alone (no key persists). Net effect: the picker always opened on
// "openrouter" and the remembered preference did nothing. initialProvider/
// initialModel are a separate channel from `active` specifically so a
// remembered-but-unvalidated preference can seed the picker without also
// rendering the "BYOK active"/"done" state, which really would be wrong when
// no key is live.
describe("ByokCliFlow initialProvider/initialModel (remembered preference, not a live key)", () => {
  it("pre-selects the given initialProvider instead of defaulting to openrouter", () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("no network in tests")));
    render(
      <ByokCliFlow
        onClose={() => {}}
        onActivate={() => {}}
        initialProvider="anthropic"
        initialModel="claude-3-5-haiku"
      />,
    );
    expect(screen.getByText("anthropic").closest("li")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("openrouter").closest("li")).toHaveAttribute("aria-selected", "false");
  });

  it("does not render the active/done state just because initialProvider is set (no key is live)", () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("no network in tests")));
    render(
      <ByokCliFlow
        onClose={() => {}}
        onActivate={() => {}}
        initialProvider="anthropic"
        initialModel="claude-3-5-haiku"
      />,
    );
    expect(screen.queryByText(/session only/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("BYOK providers")).toBeInTheDocument();
  });
});

describe("ByokCliFlow composed with useBYOKKey — the remembered cookie preference actually reaches the picker", () => {
  const COOKIE_NAME = "digichat_byok_pref";

  afterEach(() => {
    // Explicit path=/ so this matches (and actually clears) the path=/
    // attribute writeByokPrefCookie sets — happy-dom's cookie jar keys
    // cookies by (name, path) and won't overwrite/delete across a path
    // mismatch (see the same note in use-byok-key.test.ts).
    document.cookie = `${COOKIE_NAME}=; path=/; max-age=0`;
  });

  /** Mirrors exactly how chat-panel.tsx / embed-client.tsx / byok-settings-panel.tsx
   * wire useBYOKKey()'s return into ByokCliFlow. */
  function Wrapper() {
    const { provider, model, isSet, setKey, clearKey } = useBYOKKey();
    return (
      <ByokCliFlow
        onClose={() => {}}
        onActivate={setKey}
        onClear={clearKey}
        active={isSet ? { provider, model } : null}
        initialProvider={provider}
        initialModel={model}
      />
    );
  }

  it("opens with the cookie's remembered provider pre-selected, not openrouter, when no key is active", () => {
    document.cookie = `${COOKIE_NAME}=${encodeURIComponent(
      JSON.stringify({ p: "anthropic", m: "claude-3-5-haiku" }),
    )}; path=/`;
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("no network in tests")));

    render(<Wrapper />);

    // No live key was ever set — the "active"/"done" summary must not show.
    expect(screen.queryByText(/session only/)).not.toBeInTheDocument();
    expect(screen.getByText("anthropic").closest("li")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("openrouter").closest("li")).toHaveAttribute("aria-selected", "false");
  });
});
