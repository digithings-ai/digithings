import { maskPii } from "./pii";

const DEFAULT_SIZE = 500;
const DEFAULT_OVERLAP = 50;

export function htmlToText(html: string): string {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/&quot;/gi, '"')
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function stripQuotesAndSignature(text: string): string {
  const kept: string[] = [];
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (trimmed === "--" || trimmed.startsWith("-- ")) break;
    if (trimmed.startsWith(">")) continue;
    if (/^On .+ wrote:\s*$/i.test(trimmed)) continue;
    if (/^Am .+ schrieb.*:\s*$/i.test(trimmed)) continue;
    if (/^Sent from my /i.test(trimmed)) continue;
    kept.push(line);
  }
  return kept.join("\n").trim();
}

export function chunkWords(text: string, size = DEFAULT_SIZE, overlap = DEFAULT_OVERLAP): string[] {
  const words = text.split(/\s+/).filter((word) => word.length > 0);
  if (words.length === 0) return [];
  if (words.length <= size) return [words.join(" ")];
  const step = Math.max(1, size - overlap);
  const out: string[] = [];
  for (let index = 0; index < words.length; index += step) {
    const slice = words.slice(index, index + size);
    if (slice.length === 0) break;
    out.push(slice.join(" "));
    if (index + size >= words.length) break;
  }
  return out;
}

export function prepareBody(raw: string, contentType?: string): string {
  const asText = /html/i.test(contentType ?? "") || /<[a-z][\s\S]*>/i.test(raw) ? htmlToText(raw) : raw;
  return maskPii(stripQuotesAndSignature(asText));
}
