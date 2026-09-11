import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const styles = readFileSync(join(__dirname, 'globals.css'), 'utf8');

describe('dashboard tearsheet axis cascade', () => {
  it('keeps contribution axes compact after the app-local axis override', () => {
    const genericAxis = styles.indexOf('.ts-axis {');
    const contributionAxis = styles.indexOf(
      '.ts-axis.ts-contribution-axis { font-size: 9px; }'
    );

    expect(genericAxis).toBeGreaterThanOrEqual(0);
    expect(contributionAxis).toBeGreaterThan(genericAxis);
  });
});
