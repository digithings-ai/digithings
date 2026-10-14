// Thin per-app config: shared preset, no app-specific rules (DIG-3396).
// dashboard predates the TS preset, so `typescript: false` preserves its
// exact previous rule set (`core-web-vitals` only).
import { nextApp } from "../../eslint.base.mjs";

export default nextApp([], { typescript: false });
