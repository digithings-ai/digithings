import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { DeskPipelineFrame } from './DeskPipelineFrame';

describe('DeskPipelineFrame', () => {
  it('hides stale success while loading or failed, and shows the body when ready', () => {
    const child = createElement('p', null, 'stale success');
    const loading = renderToStaticMarkup(
      createElement(DeskPipelineFrame, { state: 'loading' }, child),
    );
    const error = renderToStaticMarkup(
      createElement(DeskPipelineFrame, { state: 'error', errorMessage: 'run failed' }, child),
    );
    const empty = renderToStaticMarkup(createElement(DeskPipelineFrame, { state: 'empty' }, child));
    const ready = renderToStaticMarkup(createElement(DeskPipelineFrame, { state: 'ready' }, child));

    expect(loading).toContain('data-testid="desk-state-loading"');
    expect(loading).not.toContain('stale success');
    expect(error).toContain('run failed');
    expect(error).not.toContain('stale success');
    expect(empty).toContain('No run for this date');
    expect(ready).toContain('stale success');
    expect(ready).toContain('data-chrome-path="/house/pipeline"');
  });
});
