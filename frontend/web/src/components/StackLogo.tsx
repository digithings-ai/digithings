/**
 * StackLogo — renders a real vendor mark (Simple Icons, MIT data) tinted to
 * --ink-soft, brand colour on hover; or a monogram chip when no mark exists.
 * Icons resolved by slug via a namespace lookup so an unknown/typo'd slug
 * degrades to a monogram rather than breaking the build.
 *
 * Brand marks are trademarks of their owners; Simple Icons provides the icon
 * data under MIT. We render monochrome by default out of respect for brand use.
 */
"use client";
import * as simpleIcons from "simple-icons";
import { type StackItem } from "../data/modules";

type SimpleIcon = { title: string; slug: string; hex: string; path: string };

function lookup(slug: string): SimpleIcon | null {
  const key = "si" + slug.charAt(0).toUpperCase() + slug.slice(1);
  const icon = (simpleIcons as unknown as Record<string, SimpleIcon>)[key];
  return icon && icon.path ? icon : null;
}

export function StackLogo({ item }: { item: StackItem }) {
  const icon = item.icon ? lookup(item.icon) : null;
  if (icon) {
    return (
      <span className="stack-chip" title={item.name}>
        <svg viewBox="0 0 24 24" width="15" height="15" className="stack-ico" style={{ ["--brand" as string]: `#${icon.hex}` }} aria-hidden="true">
          <path d={icon.path} fill="currentColor" />
        </svg>
        <span className="stack-name">{item.name}</span>
      </span>
    );
  }
  return (
    <span className="stack-chip" title={item.name}>
      <span className="stack-mono" aria-hidden="true">{item.mono ?? item.name.slice(0, 2)}</span>
      <span className="stack-name">{item.name}</span>
    </span>
  );
}

export function StackRow({ items, className }: { items: StackItem[]; className?: string }) {
  return (
    <div className={className ?? "stack-row"}>
      {items.map((it) => <StackLogo key={it.name} item={it} />)}
    </div>
  );
}
