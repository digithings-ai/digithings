"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Button } from "@digithings/ui/ui";
import { useDeskAccess } from "./desk-access";
import { deskHomeHref, lockTag } from "./desk-manifest";
import { isPublicDeskChrome } from "./public-surface";

/** Top-bar desk selector. `d` opens it. A locked desk stays visible and does not navigate. */
export function DeskPicker({ initialOpen = false }: { initialOpen?: boolean }) {
  const { manifest, desk, setDesk } = useDeskAccess();
  const router = useRouter();
  const [open, setOpen] = useState(initialOpen);
  const list = useRef<HTMLUListElement>(null);
  const btn = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      const target = event.target;
      const typing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable);
      if (event.key === "d" && !typing && !event.metaKey && !event.ctrlKey && !event.altKey) {
        event.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      list.current?.querySelector<HTMLElement>('button:not([disabled])[aria-current="true"], button:not([disabled])')?.focus();
    }
  }, [open]);

  if (!manifest || !desk) return <span className="desk-pick">desk: —</span>;

  const close = () => {
    setOpen(false);
    btn.current?.focus();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLUListElement>) => {
    const items = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not([disabled])")];
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === "ArrowDown") items[Math.min(index + 1, items.length - 1)]?.focus();
    else if (event.key === "ArrowUp") items[Math.max(index - 1, 0)]?.focus();
    else if (event.key === "Escape") close();
    else return;
    event.preventDefault();
    event.stopPropagation();
  };
  const choose = (id: string) => {
    const next = manifest.desks.find((item) => item.id === id);
    const href = next ? deskHomeHref(next) : null;
    if (!next || !href) return;
    setDesk(id);
    setOpen(false);
    router.push(href);
  };

  return (
    <div className="desk-pick">
      <Button
        ref={btn}
        type="button"
        variant="ghost"
        className="desk-toggle"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        title="Switch desk (d)"
      >
        desk: {desk.label} ▾
      </Button>
      {open ? (
        <>
          <Button type="button" variant="ghost" className="desk-scrim" aria-label="Close desks" onClick={() => setOpen(false)} />
          <ul ref={list} className="desk-list" role="listbox" aria-label="Desks" onKeyDown={onKeyDown}>
            {manifest.desks.filter((item) => isPublicDeskChrome(item)).map((item) => {
              const locked = item.access === "locked";
              return (
                <li key={item.id} role="option" aria-selected={item.id === desk.id}>
                  <Button
                    type="button"
                    variant="ghost"
                    className="desk-hit"
                    disabled={locked}
                    aria-current={item.id === desk.id ? "true" : undefined}
                    onClick={() => choose(item.id)}
                  >
                    <span className="desk-name">
                      {item.label}
                      {locked ? <span className="nav-tag">[{lockTag(item.reason)}]</span> : null}
                    </span>
                    <span className="desk-blurb">{locked ? item.reason : item.blurb}</span>
                  </Button>
                </li>
              );
            })}
          </ul>
        </>
      ) : null}
    </div>
  );
}
