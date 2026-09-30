// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { DevkitPreview } from "./devkit-preview";
import type { DigichatDeployment } from "@/lib/deploy-config/schema";

// ThreadSkinView renders nothing under happy-dom, so stand in a probe that
// reads the chrome context — this pins the preview's provider wiring (the
// live-reflection fix), not skin rendering.
vi.mock("@digithings/ui/chat/skins", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@digithings/ui/chat/skins")>();
  const { useSkinChrome } = await import("@digithings/ui/chat/stock");
  const React = await import("react");
  return {
    ...actual,
    ThreadSkinView: () => {
      const chrome = useSkinChrome();
      return React.createElement(
        "div",
        { "data-testid": "chrome-probe" },
        [
          chrome.title ?? "",
          chrome.welcome ?? "",
          chrome.placeholder ?? "",
          chrome.suggestions.join(","),
        ].join("|"),
      );
    },
  };
});

// Mirror the minimal-deployment fixture the client passes (deployment with
// chrome skin/theme + backend); keep every required field the component reads.
const DEPLOYMENT = {
  slug: "probe",
  chrome: { theme: "dark", skin: "digichat" },
  backend: { type: "digigraph" },
  models: {},
  features: {},
  gate: {},
} as unknown as DigichatDeployment;

describe("DevkitPreview header + invalid bar", () => {
  it("shows `{slug} · {skin} · {theme}` and the invalid bar with issues text", () => {
    const { container } = render(
      <DevkitPreview entryId="file:probe.yaml" deployment={DEPLOYMENT} issues={["(probe): bad"]} />,
    );
    expect(screen.getByText(/probe · digichat · dark/)).not.toBeNull();
    const bar = screen.getByTestId("devkit-preview-invalid-bar");
    expect(bar.getAttribute("role")).toBe("alert");
    expect(bar).toHaveTextContent("(probe): bad");
    expect(container.querySelector('[data-preview-slug="probe"]')).not.toBeNull();
  });

  it("unmounts the invalid bar when there are no issues", () => {
    render(<DevkitPreview entryId="file:probe.yaml" deployment={DEPLOYMENT} issues={[]} />);
    expect(screen.queryByTestId("devkit-preview-invalid-bar")).toBeNull();
  });

  it("renders draft chrome copy live (title/welcome/suggestions/placeholder)", () => {
    render(
      <DevkitPreview
        entryId="file:probe.yaml"
        deployment={
          {
            ...DEPLOYMENT,
            chrome: {
              ...DEPLOYMENT.chrome,
              title: "Probe Chat",
              welcome: { title: "Hi probe" },
              placeholder: "Ask probe",
              suggestions: ["Probe one"],
            },
          } as unknown as DigichatDeployment
        }
        issues={[]}
      />,
    );
    expect(screen.getByTestId("chrome-probe")).toHaveTextContent(
      "Probe Chat|Hi probe|Ask probe|Probe one",
    );
  });
});
