// Shared TS rules for a non-Next package (DIG-3396).
import { tsLib } from "../../eslint.base.mjs";

// scripts/trace-shot/out holds the harness bundle build.mjs writes (gitignored).
export default tsLib(["scripts/trace-shot/out/**"]);
