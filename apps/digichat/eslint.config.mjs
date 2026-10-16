// Thin per-app config: shared preset + this app's own additions (DIG-3396).
// The base-path fetch rule and the vendor/skin ignores below are digichat's
// own and stay here; everything else comes from the shared preset.
import { defineConfig, globalIgnores } from "eslint/config";
import { nextApp } from "../../eslint.base.mjs";

const eslintConfig = defineConfig([
  ...nextApp([
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
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/app/api/**"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "CallExpression[callee.name='fetch'] > Literal[value=/^\\/api\\//]",
          message:
            "Use p('/api/...') from @/lib/base-path for client-side API fetches so base-path deployments resolve correctly (#2408).",
        },
      ],
    },
  },
]);

export default eslintConfig;
