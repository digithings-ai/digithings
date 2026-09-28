/**
 * Component-contract coverage for the BYOK provider picker (#2348 AC5):
 * proves xai has UI parity with the other four providers and that the
 * pre-existing providers didn't regress.
 *
 * Asserted against SERVER-rendered output on purpose, mirroring the repo's
 * other component contracts (`ChatEmbedShell.contract.test.ts`) and
 * `@digithings/digichat-ui`'s documented reason for doing so: node
 * environment, no jsdom/happy-dom driving a live DOM -- there is no
 * interaction here that a static render can't already prove, since
 * `ProviderSettingsForm`'s initial `inputProvider` state is seeded directly
 * from the `provider` prop.
 *
 * Wave 2: the panel is the vendored kit `Sheet` (Base UI Dialog). Dialog
 * portals mount client-side only -- `renderToStaticMarkup` emits nothing for
 * the open panel (`see the null-render test below`) -- so the parity
 * assertions run against the exported `ProviderSettingsForm`, the same
 * markup the Sheet renders once mounted. The kit `Button` renders a real
 * `<button type="button" data-slot="button">`; the provider picker's
 * selected state is `aria-pressed="true"` + the `secondary` dress, and the
 * model picker is the controls-layer `Select` whose trigger shows the
 * current preset's label.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ProviderSettings, ProviderSettingsForm } from "@/components/ProviderSettings";
import { PROVIDER_LABELS, PROVIDER_MODELS, type ProviderId } from "@/lib/providerSettings";

function renderPanel(provider: ProviderId): string {
  return renderToStaticMarkup(
    <ProviderSettings
      open
      onClose={() => {}}
      apiKey=""
      provider={provider}
      model={PROVIDER_MODELS[provider][0]?.id ?? ""}
      isSet={false}
      onSave={() => {}}
      onClear={() => {}}
    />,
  );
}

function renderForm(provider: ProviderId): string {
  return renderToStaticMarkup(
    <ProviderSettingsForm
      storedKey=""
      storedProvider={provider}
      storedModel={PROVIDER_MODELS[provider][0]?.id ?? ""}
      isSet={false}
      onSave={() => {}}
      onClear={() => {}}
      onClose={() => {}}
    />,
  );
}

/** The rendered markup for a single provider picker button. */
function providerButtonHtml(html: string, label: string): string {
  const labelIdx = html.indexOf(`>${label}<`);
  expect(labelIdx).toBeGreaterThan(-1);
  const start = html.lastIndexOf("<button", labelIdx);
  const end = html.indexOf("</button>", labelIdx) + "</button>".length;
  return html.slice(start, end);
}

describe("ProviderSettings — xai has UI parity with the other providers (#2348 AC5)", () => {
  it("mounts the panel client-side only — Base UI Sheet portals render nothing server-side", () => {
    // Honest server-render posture: the kit Sheet's content is portal-mounted
    // after hydration, so the panel itself has no SSR markup. The parity
    // assertions below run against the form the Sheet renders.
    expect(renderPanel("xai")).toBe("");
  });

  it("renders xai as a provider option alongside all four pre-existing providers", () => {
    const html = renderForm("openrouter");
    for (const id of Object.keys(PROVIDER_LABELS) as ProviderId[]) {
      expect(html).toContain(`>${PROVIDER_LABELS[id]}<`);
    }
    expect(PROVIDER_LABELS.xai).toBe("xAI");
  });

  it("marks xai as the selected provider button when it is the selected provider", () => {
    const html = renderForm("xai");
    const xaiButton = providerButtonHtml(html, "xAI");
    expect(xaiButton).toContain('aria-pressed="true"');
    expect(xaiButton).toContain("bg-secondary");

    // The other four are present but not selected.
    for (const id of ["openrouter", "openai", "anthropic", "gemini"] as ProviderId[]) {
      const otherButton = providerButtonHtml(html, PROVIDER_LABELS[id]);
      expect(otherButton).toContain('aria-pressed="false"');
      expect(otherButton).toContain("border-border");
    }
  });

  it("shows the xai- prefixed key placeholder when xai is the selected provider (post-fix-3)", () => {
    const html = renderForm("xai");
    expect(html).toContain('placeholder="xai-…"');
  });

  it("shows xai's default preset as the model select's current value", () => {
    // The controls-layer Select renders the selected label in its trigger;
    // the popup's option list itself mounts client-side with the popup.
    const html = renderForm("xai");
    expect(html).toContain('data-slot="select-trigger"');
    expect(html).toContain("Grok 4.3");
  });

  it("still shows the correct placeholder for each pre-existing provider (no regression)", () => {
    expect(renderForm("openrouter")).toContain('placeholder="sk-or-v1-…"');
    expect(renderForm("anthropic")).toContain('placeholder="sk-ant-…"');
    expect(renderForm("gemini")).toContain('placeholder="AI…"');
    expect(renderForm("openai")).toContain('placeholder="sk-…"');
  });

  it("still selects each pre-existing provider's default model preset (no regression)", () => {
    expect(renderForm("openai")).toContain("GPT-4o mini");
    expect(renderForm("anthropic")).toContain("Claude Sonnet 4");
    expect(renderForm("gemini")).toContain("Gemini 2.5 Flash");
    expect(renderForm("openrouter")).toContain("GPT-4o mini");
  });
});
