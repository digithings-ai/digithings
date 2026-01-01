"use client";

/**
 * Tool on/off lives in `/tools`. This used to render web-search and
 * force-tool chips on the product host. It stays so a mount cannot flip tools.
 */

import type { DigichatClientConfig } from "@/lib/deploy-config";

export type ToolCatalogBarProps = {
  clientConfig: DigichatClientConfig;
  sessionKey: string;
  webSearchScope?: string;
  className?: string;
  onWebSearchChange?: (enabled: boolean) => void;
};

export function ToolCatalogBar(props: ToolCatalogBarProps): null {
  void props;
  return null;
}
