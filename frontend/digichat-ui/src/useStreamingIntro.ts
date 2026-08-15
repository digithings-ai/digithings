"use client";

import { useEffect, useState } from "react";

export function useStreamingIntro(fullText: string, enabled = true): { text: string; done: boolean } {
  const [text, setText] = useState("");

  useEffect(() => {
    if (!enabled || !fullText) {
      setText("");
      return;
    }
    if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setText(fullText);
      return;
    }
    let i = 0;
    const step = Math.max(2, Math.ceil(fullText.length / 110));
    const id = window.setInterval(() => {
      i += step;
      setText(fullText.slice(0, i));
      if (i >= fullText.length) window.clearInterval(id);
    }, 16);
    return () => window.clearInterval(id);
  }, [fullText, enabled]);

  return { text: enabled ? text : "", done: !enabled || !fullText || text.length >= fullText.length };
}
