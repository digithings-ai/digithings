/**
 * Deterministic stand-in for the digivoice backend (DIG-2698, ADR D7).
 *
 * digivoice reads through a local CLI rather than HTTP, so the deterministic
 * backend is the fixture CLI in `src/fixture-cli.ts`. This module resolves its
 * absolute path so the exporter can put it in `DIGIVOICE_BIN` before the client
 * module loads.
 */
import { resolve } from "node:path";

export const FIXTURE_CLI = resolve(import.meta.dir, "./fixture-cli.ts");
