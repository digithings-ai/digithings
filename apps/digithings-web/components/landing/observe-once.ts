/**
 * Fire `onEnter` the first time `target` scrolls into view, then stop observing.
 * Falls back to firing immediately where IntersectionObserver is unavailable, so
 * a gated animation can never stay hidden. Returns a disposer.
 */
export function observeOnce(
  target: Element,
  onEnter: () => void,
  threshold = 0.2,
  Observer: typeof IntersectionObserver | undefined = typeof IntersectionObserver === "undefined"
    ? undefined
    : IntersectionObserver,
): () => void {
  if (!Observer) {
    onEnter();
    return () => {};
  }
  let fired = false;
  const observer = new Observer(
    (entries) => {
      if (fired || !entries.some((entry) => entry.isIntersecting)) return;
      fired = true;
      observer.disconnect();
      onEnter();
    },
    { threshold },
  );
  observer.observe(target);
  return () => observer.disconnect();
}
