import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import PayloadKeyValueView from './PayloadKeyValueView';

describe('PayloadKeyValueView', () => {
  it('renders large collections in bounded pages without raw JSON', () => {
    const payload = Object.fromEntries(
      Array.from({ length: 25 }, (_, index) => [`field_${index + 1}`, `value-${index + 1}`]),
    );
    const html = renderToStaticMarkup(createElement(PayloadKeyValueView, { payload }));

    expect(html).toContain('value-1');
    expect(html).toContain('value-20');
    expect(html).not.toContain('value-21');
    expect(html).toContain('Show 5 more · 5 remaining');
    expect(html).not.toContain(JSON.stringify(payload));
  });

  it('defers deeply nested branches while preserving a disclosure path', () => {
    const payload = {
      level1: { level2: { level3: { level4: { level5: { final_value: 'inspectable' } } } } },
    };
    const html = renderToStaticMarkup(createElement(PayloadKeyValueView, { payload }));

    expect(html).toContain('Show nested details · 1 item');
    expect(html).not.toContain('inspectable');
    expect(html).not.toContain('{&quot;level5&quot;');
  });

  it('keeps deeply nested payloads structured at the disclosure boundary', () => {
    const html = renderToStaticMarkup(
      createElement(PayloadKeyValueView, {
        payload: {
          phase: {
            operation: {
              result: {
                evidence: {
                  source_name: 'Recorded market source',
                },
              },
            },
          },
        },
      })
    );

    expect(html).toContain('evidence');
    expect(html).toContain('Show nested details · 1 item');
    expect(html).not.toContain('Recorded market source');
    expect(html).not.toContain('<pre');
    expect(html).not.toContain('&quot;source_name&quot;');
  });
});