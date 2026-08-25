'use client';

import { ChevronsLeft, ChevronsRight, Maximize2, Minimize2, X } from 'lucide-react';

/** Desktop reader sizes shared by pipeline artifacts and twelve-x briefs (#1679). */
export type DetailPanelSize = 'default' | 'wide' | 'full';

const btnClass =
  'inline-flex shrink-0 items-center justify-center rounded-lg border border-hair text-ink-mute transition-colors hover:text-ink';

/**
 * Widen / full-screen / close controls for detail side panels.
 * Desktop-only size toggles (mobile is already full-bleed); close stays on all breakpoints.
 */
export default function DetailPanelHeaderActions({
  size,
  onSizeChange,
  onClose,
}: {
  size: DetailPanelSize;
  onSizeChange: (next: DetailPanelSize) => void;
  onClose: () => void;
}) {
  return (
    <div className="ml-3 flex shrink-0 items-center gap-1.5">
      {size !== 'full' && (
        <button
          type="button"
          aria-label={size === 'wide' ? 'Narrow panel' : 'Widen panel'}
          onClick={() => onSizeChange(size === 'wide' ? 'default' : 'wide')}
          className={`${btnClass} hidden h-8 w-8 md:inline-flex`}
        >
          {size === 'wide' ? <ChevronsRight size={14} /> : <ChevronsLeft size={14} />}
        </button>
      )}
      <button
        type="button"
        aria-label={size === 'full' ? 'Exit full screen' : 'Full screen'}
        onClick={() => onSizeChange(size === 'full' ? 'default' : 'full')}
        className={`${btnClass} hidden h-8 w-8 md:inline-flex`}
      >
        {size === 'full' ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
      </button>
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className={`${btnClass} h-11 w-11 md:h-8 md:w-8`}
      >
        <X size={18} />
      </button>
    </div>
  );
}

/** Sheet / panel width classes for digiweb SheetContent (right side). */
export function detailPanelSheetSizeClass(size: DetailPanelSize): string {
  if (size === 'full') {
    return 'w-full! max-w-none! sm:max-w-none!';
  }
  if (size === 'wide') {
    return 'w-full! max-w-[min(80vw,960px)]!';
  }
  return 'w-full! max-w-xl!';
}
