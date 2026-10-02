'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Button } from '@digithings/ui/ui';
import { DESK_OPTIONS, type DeskId } from '@/lib/desk/spine';

export function DeskPickerMenu({
  deskId,
  fxHubOnly = false,
}: {
  deskId: DeskId;
  fxHubOnly?: boolean;
}) {
  const options = fxHubOnly ? DESK_OPTIONS.filter((desk) => desk.id === 'fx-hub') : DESK_OPTIONS;
  return (
    <ul className="flex flex-col gap-1 p-2" aria-label="Desks">
      {options.map((desk) => (
        <li key={desk.id}>
          <Link
            href={desk.href}
            aria-current={desk.id === deskId ? 'true' : undefined}
            className="flex items-center justify-between gap-3 border border-transparent px-3 py-2 font-mono text-sm text-ink hover:border-hair hover:bg-ink/[0.04]"
          >
            <span>{desk.label}</span>
            {desk.badge ? <span className="text-ink-mute">[{desk.badge}]</span> : null}
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function DeskPicker({
  deskId,
  fxHubOnly = false,
  initialMenu = 'closed',
}: {
  deskId: DeskId;
  fxHubOnly?: boolean;
  initialMenu?: 'closed' | 'popover' | 'fullscreen';
}) {
  const [menu, setMenu] = useState(initialMenu);
  const options = fxHubOnly ? DESK_OPTIONS.filter((desk) => desk.id === 'fx-hub') : DESK_OPTIONS;
  const current = options.find((desk) => desk.id === deskId) ?? options[0];

  useEffect(() => {
    if (menu === 'closed') return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setMenu('closed');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [menu]);

  return (
    <div data-desk-picker="" className="relative">
      <Button
        type="button"
        variant="outline"
        size="sm"
        aria-expanded={menu !== 'closed'}
        aria-haspopup="dialog"
        onClick={() => setMenu((open) => (open === 'closed' ? 'popover' : 'closed'))}
        className="w-full justify-between font-mono"
      >
        <span>{current?.label ?? 'house'}</span>
        <span aria-hidden className="text-ink-mute">
          ▾
        </span>
      </Button>
      {menu === 'popover' ? (
        <div
          data-desk-picker-menu="popover"
          role="dialog"
          aria-label="Choose a desk"
          className="absolute left-0 top-full z-30 mt-1 w-80 border border-hair bg-surface"
        >
          <DeskPickerMenu deskId={deskId} fxHubOnly={fxHubOnly} />
          <div className="border-t border-hair p-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => setMenu('fullscreen')}>
              Fullscreen desks
            </Button>
          </div>
        </div>
      ) : null}
      {menu === 'fullscreen' ? (
        <div
          data-desk-picker-menu="fullscreen"
          role="dialog"
          aria-modal="true"
          aria-label="Choose a desk"
          className="fixed inset-0 z-50 flex flex-col bg-bg"
        >
          <div className="flex h-11 items-center justify-between border-b border-hair px-3">
            <p className="font-mono text-xs text-ink-mute uppercase">desks</p>
            <Button type="button" variant="outline" size="sm" onClick={() => setMenu('closed')}>
              Close
            </Button>
          </div>
          <div className="mx-auto w-full max-w-md pt-6">
            <DeskPickerMenu deskId={deskId} fxHubOnly={fxHubOnly} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
