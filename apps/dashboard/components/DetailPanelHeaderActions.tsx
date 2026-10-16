'use client';

import { ChevronsLeft, ChevronsRight, Maximize2, Minimize2, X } from 'lucide-react';
import { IconButton } from '@digithings/ui/ui';

/** Desktop reader sizes shared by pipeline artifacts and twelve-x briefs (#1679). */
export type DetailPanelSize = 'default' | 'wide' | 'full';

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
        <IconButton
          aria-label={size === 'wide' ? 'Narrow panel' : 'Widen panel'}
          onClick={() => onSizeChange(size === 'wide' ? 'default' : 'wide')}
          className="hidden md:inline-flex"
        >
          {size === 'wide' ? <ChevronsRight size={14} /> : <ChevronsLeft size={14} />}
        </IconButton>
      )}
      <IconButton
        aria-label={size === 'full' ? 'Exit full screen' : 'Full screen'}
        onClick={() => onSizeChange(size === 'full' ? 'default' : 'full')}
        className="hidden md:inline-flex"
      >
        {size === 'full' ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
      </IconButton>
      <IconButton
        aria-label="Close"
        onClick={onClose}
        className="h-11 w-11 md:h-8 md:w-8"
      >
        <X size={18} />
      </IconButton>
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
