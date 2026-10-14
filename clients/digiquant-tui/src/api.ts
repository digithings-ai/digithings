// Shared base URL for the digiquant API used by the TUI pages and probe.
// DIG-3400 S01: was copy-pasted in 7 files with two different const names.
export const API_BASE = (process.env.DQ_API_URL ?? "http://127.0.0.1:8788").replace(/\/+$/, "");
