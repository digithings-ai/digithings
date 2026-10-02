/**
 * @vitest-environment happy-dom
 */
import { afterEach, describe, expect, it } from 'vitest';
import { lockDocumentScroll } from './viewport';

describe('lockDocumentScroll', () => {
  afterEach(() => {
    document.documentElement.style.overflow = '';
    document.body.style.overflow = '';
  });

  it.each([1280, 1920])(
    'keeps the document from scrolling at %ipx',
    (width) => {
      Object.defineProperty(window, 'innerWidth', { value: width, configurable: true });
      const release = lockDocumentScroll(document);
      expect(window.innerWidth).toBe(width);
      expect(document.documentElement.style.overflow).toBe('hidden');
      expect(document.body.style.overflow).toBe('hidden');

      const scrolling = document.scrollingElement;
      expect(scrolling).not.toBeNull();
      if (scrolling) scrolling.scrollTop = 40;
      document.dispatchEvent(new Event('wheel', { bubbles: true, cancelable: true }));
      expect(scrolling?.scrollTop).toBe(0);

      const pane = document.createElement('div');
      pane.setAttribute('data-pane-body', '');
      document.body.appendChild(pane);
      const inner = new Event('wheel', { bubbles: true, cancelable: true });
      pane.dispatchEvent(inner);
      expect(inner.defaultPrevented).toBe(false);
      pane.remove();

      release();
      expect(document.documentElement.style.overflow).toBe('');
    },
  );
});
