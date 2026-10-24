import { createEmbedder, createPageFetcher, createTicketSource, createVectorStore } from "./clients";
import type { Env } from "./env";
import { readTicketState, ticketFreshness } from "./freshness";
import { loadJobs, syncDocs, syncTickets } from "./sync";

export type RunCounts = {
  jobs: number;
  tickets: number;
  vectors: number;
  docs: number;
  deleted: number;
  skipped: number;
};

export async function runIndex(env: Env, now = new Date()): Promise<RunCounts> {
  const jobs = await loadJobs(env.CORPUS_INDEX_KV);
  const counts: RunCounts = { jobs: jobs.length, tickets: 0, vectors: 0, docs: 0, deleted: 0, skipped: 0 };
  if (jobs.length === 0) {
    console.log(JSON.stringify({ event: "no_jobs" }));
    return counts;
  }
  const dryRun = env.DRY_RUN === "1";
  const source = createTicketSource(() => env.ZAMMAD_API_TOKEN ?? "");
  const store = createVectorStore(env.CLOUDFLARE_ACCOUNT_ID ?? "", () => env.CLOUDFLARE_API_TOKEN ?? "");
  const embedder = createEmbedder(env.AI);
  const pages = createPageFetcher();
  for (const job of jobs) {
    // Freshness is measured against the state left by the PREVIOUS run: a daily
    // clock that silently stopped shows here as an age past the threshold, even
    // on a run that then succeeds. Reading it after the sync would always be fresh.
    const freshness = ticketFreshness(
      job.id,
      await readTicketState(env.CORPUS_INDEX_KV, job.id),
      now.getTime(),
    );
    console.log(JSON.stringify({ event: "corpus_index_freshness", ...freshness }));
    if (freshness.alert) {
      console.log(
        JSON.stringify({
          event: "corpus_index_stale",
          job: job.id,
          reason: freshness.reason,
          last_success_at: freshness.lastSuccessAt,
          newest_ticket_at: freshness.newestTicketAt,
          age_hours: freshness.ageHours,
        }),
      );
    }
    const tickets = await syncTickets(job, env.CORPUS_INDEX_KV, source, store, embedder, now, dryRun);
    const docs = await syncDocs(job, env.CORPUS_INDEX_KV, pages, store, embedder, dryRun);
    counts.tickets += tickets.tickets;
    counts.vectors += tickets.vectors;
    counts.deleted += tickets.deleted + docs.deleted;
    counts.docs += docs.docs;
    counts.skipped += docs.skipped;
    console.log(
      JSON.stringify({
        event: "corpus_index_job",
        job: job.id,
        tickets: tickets.tickets,
        vectors: tickets.vectors,
        docs: docs.docs,
        deleted: tickets.deleted + docs.deleted,
        skipped: docs.skipped,
        dry_run: dryRun,
      }),
    );
  }
  return counts;
}
