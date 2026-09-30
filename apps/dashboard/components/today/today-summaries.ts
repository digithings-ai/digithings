/**
 * Shared Brief thesis shape. The former TodaySummaries doorway UI was retired
 * (never mounted from the live Brief); keep the type for DailyBriefWorkspace.
 */
export interface TodayThesis {
  id: string;
  name: string;
  status?: string | null;
  /** 0..1 thesis confidence when the pipeline published one. */
  confidence?: number | null;
}
