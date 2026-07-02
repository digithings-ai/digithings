/**
 * Data + pure helpers for the /welcome CodeSampleBand (#1218).
 *
 * Kept separate from the React component so the tab set and snippet-selection
 * logic are unit-testable under digichat's node-only vitest (no jsdom / RTL).
 * Snippets are illustrative BYOK/API usage, reusing the same
 * `api.digithings.ai/v1/chat` example form used elsewhere in the design system;
 * `claude-sonnet-5` is a current model id. BYOK = your provider key is forwarded
 * per request and never stored.
 */
export type CodeSampleId = "curl" | "python" | "typescript";

export interface CodeSample {
  id: CodeSampleId;
  label: string;
  code: string;
}

export const CODE_SAMPLES: CodeSample[] = [
  {
    id: "curl",
    label: "curl",
    code: `# BYOK — your key is forwarded per request, never stored.
curl https://api.digithings.ai/v1/chat \\
  -H "Authorization: Bearer $DIGITHINGS_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"model": "claude-sonnet-5", "message": "Summarize today filings"}'`,
  },
  {
    id: "python",
    label: "Python",
    code: `import os, requests

# BYOK — forwarded per request, never persisted.
resp = requests.post(
    "https://api.digithings.ai/v1/chat",
    headers={"Authorization": f"Bearer {os.environ['DIGITHINGS_KEY']}"},
    json={"model": "claude-sonnet-5", "message": "Summarize today filings"},
)
print(resp.json()["reply"])`,
  },
  {
    id: "typescript",
    label: "TypeScript",
    code: `// BYOK — forwarded per request, never stored.
const res = await fetch("https://api.digithings.ai/v1/chat", {
  method: "POST",
  headers: {
    Authorization: \`Bearer \${process.env.DIGITHINGS_KEY}\`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ model: "claude-sonnet-5", message: "Summarize today filings" }),
});
const { reply } = await res.json();`,
  },
];

/** Look up a sample by tab id; returns undefined for an unknown id. */
export function getSampleById(id: string): CodeSample | undefined {
  return CODE_SAMPLES.find((s) => s.id === id);
}
