import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = join(__dirname, '..', '..');
const SHELL = 'components/shell/app-shell.tsx';

function sources(dir: string): string[] {
  const out: string[] = [];
  for (const e of readdirSync(join(root, dir), { withFileTypes: true })) {
    const rel = join(dir, e.name);
    if (e.isDirectory()) out.push(...sources(rel));
    else if (/\.tsx$/.test(e.name) && !/\.test\.tsx$/.test(e.name)) out.push(rel);
  }
  return out;
}

describe('single <main> landmark', () => {
  const files = [...sources('app'), ...sources('components')];

  it('scans the page and component trees', () => {
    expect(files.length).toBeGreaterThan(50);
    expect(files).toContain(SHELL);
  });

  it('only the app shell renders <main>; pages and views never nest another', () => {
    const offenders = files.filter(
      (rel) => rel !== SHELL && /<main[\s>]/.test(readFileSync(join(root, rel), 'utf8')),
    );
    expect(offenders).toEqual([]);
  });
});
