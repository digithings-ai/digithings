/**
 * Markdown serializers for the API docs — shared by the /docs page (the
 * "copy as Markdown" buttons in DocsLayout) and the DigiVault sync generator
 * (scripts/gen-api-vault.ts), so the two never drift.
 *
 * Pure functions, no React or client-only deps; `ModuleNode` is imported as a
 * type only, so this module runs under plain Node (type-stripping) as well as
 * inside the Next.js bundle.
 */
import type { ModuleNode } from "@digithings/web";
import { apiDocs, type ModuleApiDoc, type Endpoint } from "./apiDocs";
import { type Guide } from "./sharedDocs";

export function guideToMarkdown(g: Guide): string {
  const L: string[] = [`## ${g.title}`, ""];
  for (const b of g.blocks) {
    if (b.kind === "h") L.push(`### ${b.text}`, "");
    else if (b.kind === "p") L.push(b.text, "");
    else if (b.kind === "list") {
      b.items.forEach((it) => L.push(`- ${it}`));
      L.push("");
    } else if (b.kind === "code") L.push("```" + b.lang, b.code, "```", "");
  }
  return L.join("\n").trim();
}

function endpointToMarkdown(ep: Endpoint, L: string[]): void {
  L.push(`### ${ep.method} ${ep.path}`, ep.summary, "");
  const meta = [ep.auth && `auth: ${ep.auth}`, ep.rateLimit && `rate: ${ep.rateLimit}`, ep.flag]
    .filter(Boolean)
    .join(" · ");
  if (meta) L.push(meta, "");
  if (ep.request?.length) {
    L.push("Request:");
    ep.request.forEach((f) => L.push(`- \`${f.name}\` (${f.type})${f.required ? " — required" : ""}: ${f.description}`));
    L.push("");
  }
  if (ep.responseFields?.length) {
    L.push("Response:");
    ep.responseFields.forEach((f) => L.push(`- \`${f.name}\` (${f.type}): ${f.description}`));
    L.push("");
  }
  if (ep.responseExample) L.push("Response example:", "```json", ep.responseExample, "```", "");
  ep.examples?.forEach((ex) => L.push("```" + ex.lang, ex.code, "```", ""));
}

export function moduleToMarkdown(m: ModuleNode): string {
  const d: ModuleApiDoc = apiDocs[m.id] ?? {};
  const L: string[] = [`# ${m.id}`, "", `> ${m.tagline}`, ""];
  L.push(`**Role:** ${m.role} · **Tier:** ${m.tier}`, "");
  L.push("## Overview");
  m.summary.forEach((s) => L.push(s, ""));
  if (d.authNote || d.scopes?.length) {
    L.push("## Authentication");
    if (d.authNote) L.push(d.authNote, "");
    d.scopes?.forEach((s) => L.push(`- \`${s.scope}\` — ${s.grants}`));
    L.push("");
  }
  if (d.run) {
    L.push("## Run locally");
    if (d.run.compose) L.push("```bash", d.run.compose, "```", "");
    if (d.run.standalone) L.push("```bash", d.run.standalone, "```", "");
    if (d.run.cli) L.push("```bash", d.run.cli, "```", "");
    if (d.run.mcp) L.push(`MCP: \`${d.run.mcp}\``, "");
  }
  if (d.env?.length) {
    L.push("## Configuration");
    d.env.forEach((e) => L.push(`- \`${e.name}\`${e.def ? ` (default \`${e.def}\`)` : ""}${e.required ? " — required" : ""}: ${e.description}`));
    L.push("");
  }
  if (d.endpoints?.length) {
    L.push("## Endpoints", "");
    if (d.baseUrlVar) L.push(`Base URL: \`$${d.baseUrlVar}\` (the service URL from docker-compose.yml).`, "");
    d.endpoints.forEach((ep) => endpointToMarkdown(ep, L));
  }
  if (d.publicInterface?.length) {
    L.push("## Public interface");
    d.publicInterface.forEach((it) => L.push(`- \`${it.signature}\` — ${it.description}`));
    L.push("");
  }
  if (d.mcp?.length) {
    L.push("## MCP tools");
    d.mcp.forEach((t) => L.push(`- \`${t.name}\` — ${t.description}`));
    L.push("");
  }
  if (d.notes?.length) {
    L.push("## Notes");
    d.notes.forEach((n) => L.push(`- ${n}`));
    L.push("");
  }
  L.push("## Stack", m.stack.map((s) => s.name).join(", "), "");
  if (m.related.length) L.push("## Related", m.related.join(", "), "");
  if (m.links.length) {
    L.push("## Links");
    m.links.forEach((l) => L.push(`- [${l.label}](${l.href})`));
    L.push("");
  }
  return L.join("\n").trim() + "\n";
}
