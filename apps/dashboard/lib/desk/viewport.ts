/**
 * One viewport for desk routes. The document itself does not scroll.
 * Overflow lives on `[data-pane-body]`.
 */

export function lockDocumentScroll(doc: Document): () => void {
  const root = doc.documentElement;
  const body = doc.body;
  const prevRoot = root.style.overflow;
  const prevBody = body.style.overflow;
  root.style.overflow = 'hidden';
  body.style.overflow = 'hidden';
  if (doc.scrollingElement) doc.scrollingElement.scrollTop = 0;

  const onWheel = (event: WheelEvent) => {
    const target = event.target;
    if (target instanceof Element && target.closest('[data-pane-body]')) return;
    event.preventDefault();
    if (doc.scrollingElement) doc.scrollingElement.scrollTop = 0;
  };

  doc.addEventListener('wheel', onWheel, { passive: false });
  return () => {
    doc.removeEventListener('wheel', onWheel);
    root.style.overflow = prevRoot;
    body.style.overflow = prevBody;
  };
}
