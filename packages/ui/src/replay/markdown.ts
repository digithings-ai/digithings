/** Small markdown renderer. Emits the `aui-md-*` classes the digichat sheet styles. */

import { escapeHtml } from "./escape";

export function renderMarkdown(source: string): string {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: string[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index] ?? "";
    if (line.trim() === "") {
      index += 1;
      continue;
    }
    if (line.startsWith("```")) {
      const lang = escapeHtml(line.slice(3).trim());
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !(lines[index] ?? "").startsWith("```")) {
        body.push(lines[index] ?? "");
        index += 1;
      }
      if (index < lines.length) index += 1;
      const label = lang
        ? `<div class="aui-code-header-root"><span class="aui-code-header-language">${lang}</span></div>`
        : "";
      blocks.push(
        `${label}<pre class="aui-md-pre"><code>${escapeHtml(body.join("\n"))}</code></pre>`,
      );
      continue;
    }
    if (isTableStart(lines, index)) {
      const table = readTable(lines, index);
      blocks.push(table.html);
      index = table.next;
      continue;
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1]?.length ?? 1;
      blocks.push(`<h${level} class="aui-md-h${level}">${inline(heading[2] ?? "")}</h${level}>`);
      index += 1;
      continue;
    }
    if (line.startsWith("> ")) {
      const quoted: string[] = [];
      while (index < lines.length && (lines[index] ?? "").startsWith("> ")) {
        quoted.push((lines[index] ?? "").slice(2));
        index += 1;
      }
      blocks.push(`<blockquote class="aui-md-blockquote">${inline(quoted.join(" "))}</blockquote>`);
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index] ?? "")) {
        items.push((lines[index] ?? "").replace(/^\s*[-*]\s+/, ""));
        index += 1;
      }
      blocks.push(
        `<ul class="aui-md-ul">${items.map((item) => `<li>${inline(item)}</li>`).join("")}</ul>`,
      );
      continue;
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index] ?? "")) {
        items.push((lines[index] ?? "").replace(/^\s*\d+\.\s+/, ""));
        index += 1;
      }
      blocks.push(
        `<ol class="aui-md-ol">${items.map((item) => `<li>${inline(item)}</li>`).join("")}</ol>`,
      );
      continue;
    }
    const paragraph: string[] = [line];
    index += 1;
    while (
      index < lines.length &&
      (lines[index] ?? "").trim() !== "" &&
      !blockStart(lines[index] ?? "")
    ) {
      paragraph.push(lines[index] ?? "");
      index += 1;
    }
    blocks.push(`<p class="aui-md-p">${inline(paragraph.join(" "))}</p>`);
  }
  return blocks.join("");
}

function blockStart(line: string): boolean {
  return (
    line.startsWith("```") ||
    line.startsWith("> ") ||
    /^#{1,6}\s+/.test(line) ||
    /^\s*[-*]\s+/.test(line) ||
    /^\s*\d+\.\s+/.test(line) ||
    /^\s*\|/.test(line)
  );
}

function isTableStart(lines: readonly string[], index: number): boolean {
  const header = lines[index] ?? "";
  const rule = lines[index + 1] ?? "";
  return header.includes("|") && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(rule);
}

function readTable(
  lines: readonly string[],
  index: number,
): { html: string; next: number } {
  const header = splitRow(lines[index] ?? "");
  let cursor = index + 2;
  const rows: string[][] = [];
  while (cursor < lines.length && (lines[cursor] ?? "").includes("|") && (lines[cursor] ?? "").trim()) {
    rows.push(splitRow(lines[cursor] ?? ""));
    cursor += 1;
  }
  const head = header.map((cell) => `<th>${inline(cell)}</th>`).join("");
  const body = rows
    .map((row) => `<tr>${row.map((cell) => `<td>${inline(cell)}</td>`).join("")}</tr>`)
    .join("");
  return {
    html: `<div class="aui-md-table-wrapper"><table class="aui-md-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`,
    next: cursor,
  };
}

function splitRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

function inline(source: string): string {
  let text = escapeHtml(source);
  text = text.replace(/`([^`]+)`/g, `<code class="aui-md-code">$1</code>`);
  text = text.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_match, label: string, href: string) => {
    if (!safeHref(href)) return label;
    return `<a class="aui-md-a" href="${href}" rel="noopener noreferrer">${label}</a>`;
  });
  text = text.replace(/\*\*([^*]+)\*\*/g, `<strong class="aui-md-strong">$1</strong>`);
  text = text.replace(/(^|[^\*])\*([^*]+)\*/g, `$1<em>$2</em>`);
  return text;
}

function safeHref(href: string): boolean {
  const value = href.trim().toLowerCase();
  if (value.startsWith("http://") || value.startsWith("https://") || value.startsWith("mailto:")) {
    return true;
  }
  if (value.startsWith("#") || value.startsWith("/") || value.startsWith("./")) return true;
  return false;
}
