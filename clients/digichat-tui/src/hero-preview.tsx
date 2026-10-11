/**
 * Preview one hero banner in OpenTUI, for TUI review captures before any web
 * integration: `bun src/hero-preview.tsx digillm`. Honours NO_MOTION,
 * HERO_BANNER_MOTION and HERO_BANNER_LIVE like every surface. q or Ctrl+C quits.
 */
import { createCliRenderer } from "@opentui/core";
import { createRoot, useKeyboard, useTerminalDimensions } from "@opentui/react";

import { BANNERS } from "../../../packages/hero-banner/src/definitions";
import { HeroBanner } from "./hero-banner";

function Preview({ id, onQuit }: { id: keyof typeof BANNERS; onQuit: () => void }) {
  const { width, height } = useTerminalDimensions();
  useKeyboard((key) => {
    if (key.name === "q") onQuit();
  });
  const def = BANNERS[id];
  return (
    <box width="100%" height="100%" flexDirection="column" justifyContent="center">
      <HeroBanner def={def} cols={width} rows={height} />
      <box height={1} />
      <text fg="#5F5F5F">{`  ${def.label} · ${width}x${height} · q quits`}</text>
    </box>
  );
}

if (import.meta.main) {
  const id = (process.argv[2] ?? "digillm") as keyof typeof BANNERS;
  if (!(id in BANNERS)) {
    console.error(`unknown banner "${id}". One of: ${Object.keys(BANNERS).join(", ")}`);
    process.exit(2);
  }
  const renderer = await createCliRenderer({ exitOnCtrlC: true });
  createRoot(renderer).render(<Preview id={id} onQuit={() => renderer.destroy()} />);
}
