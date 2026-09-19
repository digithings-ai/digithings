import type { DocsToolId, DocsToolParameterSchema } from "@/lib/docs/types";
import { z } from "zod";

export function buildDocsToolParameters(toolId: DocsToolId): DocsToolParameterSchema {
  switch (toolId) {
    case "searchDocs":
      return z.object({
        query: z.string().min(1),
        limit: z.number().int().min(1).max(5).optional(),
      });
    case "openPage":
      return z.object({
        pageId: z.string().min(1),
      });
    case "generateCodeSnippet":
      return z.object({
        topic: z.string().min(1),
        language: z.enum(["curl", "typescript", "python"]).optional(),
      });
    default:
      return z.record(z.string(), z.unknown());
  }
}
