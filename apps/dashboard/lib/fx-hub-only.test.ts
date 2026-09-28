import { describe, expect, it } from 'vitest';
import { isFxHubOnlyAllowedPath } from './fx-hub-only';

describe('isFxHubOnlyAllowedPath', () => {
  it('allows the FX Hub subtree (with and without the static-export base)', () => {
    expect(isFxHubOnlyAllowedPath('/twelve-x')).toBe(true);
    expect(isFxHubOnlyAllowedPath('/twelve-x/')).toBe(true);
    expect(isFxHubOnlyAllowedPath('/twelve-x/metrics')).toBe(true);
    expect(isFxHubOnlyAllowedPath('/dashboard/twelve-x')).toBe(true);
    expect(isFxHubOnlyAllowedPath('/dashboard/twelve-x/metrics')).toBe(true);
  });

  it('allows account settings', () => {
    expect(isFxHubOnlyAllowedPath('/settings')).toBe(true);
    expect(isFxHubOnlyAllowedPath('/settings/billing')).toBe(true);
    expect(isFxHubOnlyAllowedPath('/dashboard/settings')).toBe(true);
  });

  it('blocks every other surface', () => {
    expect(isFxHubOnlyAllowedPath('/')).toBe(false);
    expect(isFxHubOnlyAllowedPath('/dashboard')).toBe(false);
    expect(isFxHubOnlyAllowedPath('/dashboard/')).toBe(false);
    expect(isFxHubOnlyAllowedPath('/portfolio')).toBe(false);
    expect(isFxHubOnlyAllowedPath('/portfolio/performance')).toBe(false);
    expect(isFxHubOnlyAllowedPath('/pipeline')).toBe(false);
    expect(isFxHubOnlyAllowedPath('/research')).toBe(false);
    expect(isFxHubOnlyAllowedPath('/twelve-x-files')).toBe(false);
  });
});
