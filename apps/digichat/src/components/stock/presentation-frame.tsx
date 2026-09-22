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

type ChromeMode = DigichatClientConfig["chrome"]["mode"];

/** True for the modes that mount the chat inside a frame rather than the page. */
export function isFramedPresentation(mode: ChromeMode): boolean {
  return mode === "modal" || mode === "sidebar";
}

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
  const label = chrome.launcher?.label ?? chrome.title ?? "digichat";

  if (mode === "modal") {
    return (
      <DigichatLauncher
        title={chrome.title ?? "digichat"}
        ariaLabel={label}
        hotkey={chrome.launcher?.hotkey}
        className="digichat-presentation digichat-presentation--modal"
      >
        {children}
      </DigichatLauncher>
    );
  }

  if (mode === "sidebar") {
    return (
      <div
        className="digichat-presentation digichat-presentation--sidebar"
        data-chrome-mode="sidebar"
      >
        <div className="digichat-presentation__canvas" aria-hidden="true" />
        <aside className="digichat-presentation__panel" aria-label={label}>
          {children}
        </aside>
      </div>
    );
  }

  return <>{children}</>;
}
