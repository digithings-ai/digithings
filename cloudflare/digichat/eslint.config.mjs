import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/app/api/**"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "CallExpression[callee.name='fetch'] > Literal[value=/^\\/api\\//]",
          message:
            "Use p('/api/...') from @/lib/base-path for client-side API fetches so base-path deployments resolve correctly (#2408).",
        },
      ],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    ".next-*/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Vendor copies / separate packages — not the product lint surface.
    "reference/**",
    "cli/**",
    "src/app/(baseline)/**",
    "src/components/assistant-ui/skins/base/**",
    "src/components/assistant-ui/skins/webpage-assistant/**",
    "src/components/assistant-ui/skins/product-page-assistant/**",
    "src/components/assistant-ui/skins/chatgpt.tsx",
    "src/components/assistant-ui/skins/claude.tsx",
    "src/components/assistant-ui/skins/gemini.tsx",
    "src/components/assistant-ui/skins/grok.tsx",
    "src/components/assistant-ui/skins/perplexity.tsx",
    "src/components/assistant-ui/skins/expo-react-native.tsx",
    "src/components/assistant-ui/skins/react-ink.tsx",
  ]),
]);

export default eslintConfig;
