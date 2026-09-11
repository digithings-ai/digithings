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
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ProviderSettings } from "@/components/ProviderSettings";
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

/** The rendered markup for a single provider picker button. */
function providerButtonHtml(html: string, label: string): string {
  const labelIdx = html.indexOf(`>${label}<`);
  expect(labelIdx).toBeGreaterThan(-1);
  const start = html.lastIndexOf("<button", labelIdx);
  const end = html.indexOf("</button>", labelIdx) + "</button>".length;
  return html.slice(start, end);
}

describe("ProviderSettings — xai has UI parity with the other providers (#2348 AC5)", () => {
  it("renders xai as a provider option alongside all four pre-existing providers", () => {
    const html = renderPanel("openrouter");
    for (const id of Object.keys(PROVIDER_LABELS) as ProviderId[]) {
      expect(html).toContain(`>${PROVIDER_LABELS[id]}<`);
    }
    expect(PROVIDER_LABELS.xai).toBe("xAI");
  });

  it("marks xai as the active provider button when it is the selected provider", () => {
    const html = renderPanel("xai");
    const xaiButton = providerButtonHtml(html, "xAI");
    expect(xaiButton).toContain("is-active");

    // The other four are present but not active.
    for (const id of ["openrouter", "openai", "anthropic", "gemini"] as ProviderId[]) {
      const otherButton = providerButtonHtml(html, PROVIDER_LABELS[id]);
      expect(otherButton).not.toContain("is-active");
    }
  });

  it("shows the xai- prefixed key placeholder when xai is the selected provider (post-fix-3)", () => {
    const html = renderPanel("xai");
    expect(html).toContain('placeholder="xai-…"');
  });

  it("populates the model select with xai's presets, matching the other providers' pattern", () => {
    const html = renderPanel("xai");
    expect(html).toContain("Grok 4.3");
    expect(html).toContain("Grok 4.5");
  });

  it("still shows the correct placeholder for each pre-existing provider (no regression)", () => {
    expect(renderPanel("openrouter")).toContain('placeholder="sk-or-v1-…"');
    expect(renderPanel("anthropic")).toContain('placeholder="sk-ant-…"');
    expect(renderPanel("gemini")).toContain('placeholder="AI…"');
    expect(renderPanel("openai")).toContain('placeholder="sk-…"');
  });

  it("still renders every pre-existing provider's model presets (no regression)", () => {
    expect(renderPanel("openai")).toContain("GPT-4o mini");
    expect(renderPanel("anthropic")).toContain("Claude Sonnet 4");
    expect(renderPanel("gemini")).toContain("Gemini 2.5 Flash");
    expect(renderPanel("openrouter")).toContain("GPT-4o mini");
  });
});
