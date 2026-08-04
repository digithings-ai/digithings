"use client";

/**
 * Read embed UI overrides from the iframe URL after mount.
 *
 * Why not `useMemo(() => readEmbedUiParams(window.location.search), [])`?
 * That factory returns `{}` during SSR (`window` missing). On the client,
 * React 19 / Next hydration can keep the server-computed memo value (or
 * recover from a style-attribute mismatch by retaining the server DOM), so
 * the wrapper's `style` stays null even though `location.search` has a valid
 * `?accent=%23b5562b`. Welcome/suggestions often still "work" because they
 * also arrive from the tenant-config fetch, which triggers a later client
 * re-render — but if the live registry omits `accent` (or the URL is the
 * only source), terracotta never applies.
 *
 * useState + useEffect matches the post-mount read pattern already used for
 * embed auth (`readEmbedUrlAuth` in use-embed-digi-chat.ts): first paint is
 * empty on both server and client (no hydration mismatch), then one effect
 * applies URL overrides.
 */

import { useEffect, useState } from "react";
import { readEmbedUiParams, type EmbedUiParams } from "@/lib/embed-ui-params";

const EMPTY: EmbedUiParams = {};

export function useEmbedUiParams(): EmbedUiParams {
  const [params, setParams] = useState<EmbedUiParams>(EMPTY);

  useEffect(() => {
    setParams(readEmbedUiParams(window.location.search));
  }, []);

  return params;
}
