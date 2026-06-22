import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import ArchitecturePage from './page';

describe('ArchitecturePage', () => {
  it('renders the title, both sub-graphs, and real phase-file tokens', () => {
    const html = renderToStaticMarkup(createElement(ArchitecturePage));

    expect(html).toContain('<h1');
    expect(html).toContain('How Olympus works');
    expect(html).toContain('Phase map');
    // Both halves are documented — the old page omitted Hermes entirely.
    expect(html).toContain('Atlas — research graph');
    expect(html).toContain('Hermes — portfolio graph');
    expect(html).toContain('<code');
    expect(html).toContain('atlas/phases/phase1_altdata.py');
    expect(html).toContain('hermes/phases/h9_commit_run.py');

    // Guard against the stale pipeline rotting back in: the old page linked
    // deleted files and a removed cadence tier.
    expect(html).not.toContain('phase7c_analyst');
    expect(html).not.toContain('phase7cd_debate');
    expect(html).not.toContain('Monthly Synthesis');
  });
});
