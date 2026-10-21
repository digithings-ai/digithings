import type { CSSProperties, ReactNode } from "react";

/**
 * Accessible name that must not paint.
 *
 * Not Tailwind's `.sr-only`. That utility is emitted only when the app that
 * consumes this package happens to scan the class, so a shared component that
 * leans on it renders the name as a second copy of the label. No `left`
 * offset: a box shifted off to the side still paints in some hosts. Clip it
 * to a 1px box, in place, with overflow hidden.
 */
export const screenReaderOnlyStyle: CSSProperties = {
  position: "absolute",
  width: "1px",
  height: "1px",
  padding: 0,
  margin: 0,
  overflow: "hidden",
  clipPath: "inset(50%)",
  whiteSpace: "nowrap",
  border: 0,
};

export function ScreenReaderOnly({ children }: { children: ReactNode }) {
  return (
    <span data-slot="screen-reader-name" style={screenReaderOnlyStyle}>
      {children}
    </span>
  );
}
