"use client";

import { useEffect, useRef, useState } from "react";

import { observeOnce } from "./observe-once";
import { PixelWordmark } from "./PixelWordmark";

/** The closing mark above the footer. Builds once, the first time it scrolls into view. */
export function FooterWordmark() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [live, setLive] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    return observeOnce(node, () => setLive(true));
  }, []);

  return (
    <div className="pixel-word-band" ref={ref}>
      <PixelWordmark variant="footer" live={live} />
    </div>
  );
}
