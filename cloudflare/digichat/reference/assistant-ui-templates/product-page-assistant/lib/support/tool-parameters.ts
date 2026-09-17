import type { SupportToolId, SupportToolParameterSchema } from "@/lib/support/types";
import { z } from "zod";

const attachmentSchema = z.object({
  name: z.string(),
  type: z.string().optional(),
});

export function buildSupportToolParameters(toolId: SupportToolId): SupportToolParameterSchema {
  switch (toolId) {
    case "analyzeIssue":
      return z.object({
        description: z.string(),
        service: z.string().optional(),
        attachments: z.array(attachmentSchema).optional(),
        scenarioId: z.enum(["sync_failure", "auth_error"]).optional(),
      });
    case "createSupportSummary":
      return z.object({
        issue: z.any(),
        attachments: z.array(attachmentSchema).optional(),
        scenarioId: z.enum(["sync_failure", "auth_error"]).optional(),
      });
    default:
      return z.record(z.string(), z.unknown());
  }
}
