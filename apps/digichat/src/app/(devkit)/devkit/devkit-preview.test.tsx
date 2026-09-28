// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DevkitPreview } from "./devkit-preview";
import type { DigichatDeployment } from "@/lib/deploy-config/schema";

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
});
