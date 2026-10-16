import { expect, test } from "bun:test";
import { strategyBlocks } from "./shape";
import { strategySheetBody } from "./strategy-sheet";

test("an unpublished strategy tearsheet is dashes and not a lecture", () => {
  const painted = strategyBlocks(strategySheetBody(null));
  const text = JSON.stringify(painted);
  expect(text).toContain("CAGR");
  expect(text).toContain("—");
  expect(text).not.toContain("official API");
  expect(text).not.toContain("This read returned no values.");
  expect(text).not.toContain("Backtest only");
  expect(painted.blocks.some((block) => block.kind === "chart")).toBe(false);
});

test("two real equity points paint a chart", () => {
  const painted = strategyBlocks(
    strategySheetBody({
      equity_curve: [
        { t: "2024-01-01", v: 1 },
        { t: "2024-02-01", v: 2 },
      ],
    }),
  );
  expect(painted.blocks.some((block) => block.kind === "chart" && block.text === "▁█")).toBe(true);
});
