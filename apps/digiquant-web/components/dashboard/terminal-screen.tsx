"use client";

import { BriefPage } from "@/components/desk/pages/brief";
import { FxDesk, isFxPath } from "@/components/desk/pages/fx";
import { PipelinePage } from "@/components/desk/pages/pipeline";
import { isPortfolioPath, PortfolioPages } from "@/components/desk/pages/portfolio";
import { StrategiesPages } from "@/components/desk/pages/strategies";

const STRATEGY_PATHS = new Set(["/strategies", "/strategies/detail", "/strategies/deploy"]);

export type ScreenKind = "brief" | "portfolio" | "pipeline" | "strategies" | "fx" | "undrawn";

/** Which real desk screen a terminal path draws. Web-only slots stay undrawn. */
export function screenKind(path: string): ScreenKind {
  if (path === "/brief") return "brief";
  if (path === "/pipeline") return "pipeline";
  if (STRATEGY_PATHS.has(path)) return "strategies";
  if (isPortfolioPath(path)) return "portfolio";
  if (isFxPath(path)) return "fx";
  return "undrawn";
}

/** The screens the desk already draws for those OpenTUI pages. */
export function TerminalScreen({ path }: { path: string }) {
  const kind = screenKind(path);
  switch (kind) {
    case "brief":
      return <BriefPage />;
    case "portfolio":
      return <PortfolioPages path={path} />;
    case "pipeline":
      return <PipelinePage />;
    case "strategies":
      return <StrategiesPages path={path} />;
    case "fx":
      return <FxDesk path={path} />;
    case "undrawn":
      return (
        <p className="m-0 px-3 py-6 text-[0.75rem] leading-[1.5] text-ink-mute">
          This page is not drawn on the terminal.
        </p>
      );
    default: {
      const never: never = kind;
      return never;
    }
  }
}
