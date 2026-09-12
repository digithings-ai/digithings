import { defaultBrandTheme, supportAssistantConfig } from "@/lib/support/assistant-config";
import { supportSettings } from "@/lib/support/settings";
import { supportToolData } from "@/lib/support/tool-data";

export type { SupportScenarioPack } from "@/lib/support/types";
export type { SupportScenarioId } from "@/lib/support/types";

export const supportTemplateConfig = {
  assistant: supportAssistantConfig,
  brandTheme: defaultBrandTheme,
  ...supportSettings,
  toolData: supportToolData,
} as const;
