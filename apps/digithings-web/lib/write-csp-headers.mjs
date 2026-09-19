/**
 * Writes public/_headers with frame-src from NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN.
 * Invoked as npm prebuild so next export ships a CSP that matches the iframe.
 */
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { frameSrcForCsp, renderCloudflareHeaders } from "./security-headers.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const outPath = join(root, "public", "_headers");
const frameSrc = frameSrcForCsp();
writeFileSync(outPath, renderCloudflareHeaders(frameSrc), "utf8");
console.log(`wrote ${outPath} (frame-src ${frameSrc})`);
