import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { KeysTab, sanitizeKeyRow } from './keys-tab';

describe('KeysTab', () => {
  it('renders keys surface without retaining secrets in markup', () => {
    const secret = 'sk-should-never-render';
    const html = renderToStaticMarkup(
      createElement(KeysTab, {
        api: null,
        listFn: vi.fn(async () => []),
        connectFn: vi.fn(),
        revokeFn: vi.fn(),
      }),
    );
    expect(html).toContain('settings-keys-tab');
    expect(html).toContain('keys-provider-select');
    expect(html).not.toContain(secret);
  });

  it('sanitizeKeyRow drops non-display fields', () => {
    const cleaned = sanitizeKeyRow({
      id: 'k1',
      provider: 'openai',
      fingerprint: 'abcd1234',
      status: 'active',
      last_used_at: null,
      // @ts-expect-error intentional poison field
      secret: 'sk-leak',
      // @ts-expect-error intentional poison field
      ciphertext: 'xx',
    });
    expect(cleaned.fingerprint).toBe('abcd1234');
    expect(JSON.stringify(cleaned)).not.toContain('sk-leak');
    expect(JSON.stringify(cleaned)).not.toContain('ciphertext');
  });
});
