// @vitest-environment happy-dom
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ComponentType, ReactNode } from "react";

vi.mock("@/components/echarts-card", () => ({
  EChartsCard: ({ spec }: { spec: Record<string, unknown> }) => (
    <div data-testid="chart">{String(spec.title ?? "chart")}</div>
  ),
}));

import { JsonChartFence } from "./markdown-text";

const Pre: ComponentType<{ children?: ReactNode }> = ({ children }) => <pre>{children}</pre>;
const Code: ComponentType<{ children?: ReactNode }> = ({ children }) => <code>{children}</code>;

describe("JsonChartFence", () => {
  it("renders ECharts for a chart envelope", () => {
    render(
      <JsonChartFence
        language="json"
        code={JSON.stringify({ type: "chart", spec: { title: "equity" } })}
        components={{ Pre, Code }}
      />,
    );
    expect(screen.getByTestId("chart").textContent).toBe("equity");
  });

  it("falls back to a code block for ordinary JSON", () => {
    render(
      <JsonChartFence
        language="json"
        code='{"ok":true}'
        components={{ Pre, Code }}
      />,
    );
    expect(screen.queryByTestId("chart")).toBeNull();
    expect(screen.getByText('{"ok":true}')).toBeTruthy();
  });
});
