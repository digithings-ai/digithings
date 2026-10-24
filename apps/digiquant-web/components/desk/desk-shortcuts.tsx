"use client";

import { SHORTCUTS } from "./shortcuts";

/** The `?` overlay. Lists the same map the handler uses. */
export function DeskShortcuts({ onClose }: { onClose: () => void }) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg border border-hair bg-black p-4 font-mono text-[0.75rem] text-ink"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <span>keyboard shortcuts</span>
          <button type="button" className="text-ink/60 hover:text-ink" onClick={onClose} autoFocus>
            esc
          </button>
        </div>
        <table className="w-full border-collapse">
          <tbody>
            {SHORTCUTS.map((s) => (
              <tr key={s.keys} className="border-t border-hair align-top">
                <td className="whitespace-nowrap py-1 pr-4 text-ink">{s.keys}</td>
                <td className="py-1 text-ink/70">{s.does}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
