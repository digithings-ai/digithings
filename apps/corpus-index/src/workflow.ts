import { WorkflowEntrypoint, type WorkflowEvent, type WorkflowStep } from "cloudflare:workers";
import type { Env } from "./env";
import { runIndex } from "./run";

export type IndexParams = { reason?: string };

export class CorpusIndexWorkflow extends WorkflowEntrypoint<Env, IndexParams> {
  async run(_event: WorkflowEvent<IndexParams>, step: WorkflowStep): Promise<{ jobs: number }> {
    return step.do("index", async () => {
      const counts = await runIndex(this.env);
      return { jobs: counts.jobs, tickets: counts.tickets, vectors: counts.vectors, docs: counts.docs };
    });
  }
}
