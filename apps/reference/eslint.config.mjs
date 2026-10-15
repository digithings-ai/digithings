// Thin per-app config: shared preset + vendor-copy ignores (DIG-3396).
import { nextApp } from "../../eslint.base.mjs";

export default nextApp([
  // Vendor assistant-ui / catalog copies — not product lint surface.
  "components/ui/dot-matrix.tsx",
  "app/(chatbot)/**",
  "components/chatbot/**",
]);
