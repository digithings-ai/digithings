import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Vendor assistant-ui / catalog copies — not product lint surface.
    "components/ui/dot-matrix.tsx",
    "app/(chatbot)/**",
    "components/chatbot/**",
  ]),
]);

export default eslintConfig;
