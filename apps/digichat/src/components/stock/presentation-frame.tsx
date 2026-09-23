"use client";

/**
 * Config-driven presentation for `chrome.mode: modal` and `chrome.mode: sidebar`
 * (#4515). Before this, both modes were folded into the `/embed` redirect, so a
 * deployment that asked for a pop-up or a docked panel got the bare iframe
 * surface instead.
 *
 * The frame only decides WHERE the chat renders; the chat itself is the same
 * `ProductStockShell` the `app` mode mounts, so skin, chrome and theme stay
 * identical across modes.
 */

import type { ReactNode } from "react";
import { DigichatLauncher } from "@digithings/ui/chat/launcher";
import type { DigichatClientConfig } from "@/lib/deploy-config";
import { isFramedPresentation, skinOwnsPageChrome } from "@/lib/thread-skins";

type ChromeMode = DigichatClientConfig["chrome"]["mode"];

// Re-exported so existing callers keep resolving it here. The definition lives
// in `lib/thread-skins` (server-safe) — see the comment there.
export { isFramedPresentation };

export function PresentationFrame({
  mode,
  clientConfig,
  children,
}: {
  mode: ChromeMode;
  clientConfig: DigichatClientConfig;
  children: ReactNode;
}) {
  const chrome = clientConfig.chrome;

  // Layout skins (docs / dashboard / expo) own the whole page — a launcher
  // panel or a 380px dock would strip the template they render. They keep the
  // page even when `chrome.mode` asks for a frame.
  if (skinOwnsPageChrome(chrome.skin)) {
    return <>{children}</>;
  }

  const label = chrome.launcher?.label ?? chrome.title ?? "digichat";

  if (mode === "modal") {
    return (
      <DigichatLauncher
        title={chrome.title ?? "digichat"}
        ariaLabel={label}
        hotkey={chrome.launcher?.hotkey}
        className="dc-presentation dc-presentation--modal"
      >
        {children}
      </DigichatLauncher>
    );
  }

  if (mode === "sidebar") {
    return (
      <div
        className="dc-presentation dc-presentation--sidebar"
        data-chrome-mode="sidebar"
      >
        <div className="dc-presentation__canvas" aria-hidden="true" />
        <aside className="dc-presentation__panel" aria-label={label}>
          {children}
        </aside>
      </div>
    );
  }

  return <>{children}</>;
}
