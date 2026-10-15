"use client";

// Single source of truth lives in `../../stock/use-copy-to-clipboard`
// (byte-identical fork removed, S24 review). This shim preserves the
// gallery-thread import path.
export {
  useCopyToClipboard,
  type UseCopyToClipboardOptions,
} from "../../stock/use-copy-to-clipboard";
