import { createCliRenderer } from "@opentui/core";
import { createRoot } from "@opentui/react";
import { App } from "./app";

if (import.meta.main) {
  const renderer = await createCliRenderer({ exitOnCtrlC: true });
  createRoot(renderer).render(<App />);
}
