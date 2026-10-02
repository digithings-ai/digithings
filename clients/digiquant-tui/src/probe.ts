import { BLOCKS, PAGES, PAGE_LAYOUTS } from "./catalog";
import { readBlock } from "./read";

const api = (process.env.DQ_API_URL ?? "http://127.0.0.1:8788").replace(/\/+$/, "");

const seen = new Map<string, { kind: "fields" | "graph"; blocks: string[] }>();
for (const page of PAGES) {
  for (const placement of PAGE_LAYOUTS[page.path] ?? []) {
    const block = BLOCKS[placement.id];
    if (!block) continue;
    const cur = seen.get(block.route) ?? { kind: block.kind, blocks: [] };
    cur.blocks.push(`${page.path} ${block.id}`);
    seen.set(block.route, cur);
  }
}

const rows = await Promise.all(
  [...seen.entries()].map(async ([route, meta]) => {
    const result = await readBlock(api, route, meta.kind);
    return { route, status: result.status, line: result.lines[0] ?? "", blocks: meta.blocks };
  }),
);

for (const row of rows) {
  console.log(`${row.status.padEnd(6)} ${row.route}`);
  console.log(`       ${row.line}`);
}
