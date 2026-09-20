import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const styles = readFileSync(join(__dirname, 'globals.css'), 'utf8');

describe('dashboard tearsheet layer (Q3b slice 4)', () => {
  // The former §13 screen variants (tighter panels/KPIs, .ts-btn/.ts-notes
  // additions, SVG axis rules) are deleted: no dashboard markup consumes them
  // and no kit component this app renders emits them — the shared
  // finance-tearsheet family sheet is the single source (#4443).
  it('carries no dashboard-local ts- screen variants', () => {
    for (const rule of [
      '.ts-panel {',
      '.ts-kpi {',
      '.ts-btn {',
      '.ts-axis {',
      '.ts-notes {',
      '.ts-subhead {',
      '.ts-performance-kpis {',
      '.ts-header {',
      '.ts-h1 {',
    ]) {
      expect(styles).not.toContain(rule);
    }
  });

  it('keeps dashboard print geometry (shell hides, @page, ts-page padding)', () => {
    expect(styles).toContain('#app-sidebar-nav');
    expect(styles).toContain('@page { margin: 0; }');
    expect(styles).toContain('.ts-page { padding: 14mm 13mm; }');
  });
});
