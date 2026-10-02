/** Fixed pair of dashed vertical hairlines at the frame edges: the page reads as
 *  one built object. Utilities only; swap for the kit's LayoutLines once the
 *  refactor branch lands it. */
export function LayoutRails() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
      <div className="mx-auto h-full w-full max-w-[calc(var(--frame-w)+2*var(--page-pad))] border-x border-dashed border-hair" />
    </div>
  );
}
