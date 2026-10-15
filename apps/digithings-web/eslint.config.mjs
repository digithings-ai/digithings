// Thin per-app config: shared preset + prebuild-copy ignores (DIG-3396).
// `public/swagger-ui` / `public/openapi` are gitignored prebuild copies —
// never lint vendored swagger-ui or synced specs.
import { nextApp } from "../../eslint.base.mjs";

export default nextApp(["public/swagger-ui/**", "public/openapi/**"]);
