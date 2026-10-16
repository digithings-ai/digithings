-- 006_fix_partitioned_rls.sql — Re-enable RLS on partitioned tables.
-- Migration 004 renamed daily_snapshots_partitioned → daily_snapshots and
-- documents_partitioned → documents, but RLS was not re-enabled on the new
-- parent tables or their year/default partitions.
-- Safe to re-run (ENABLE RLS is idempotent; DROP POLICY IF EXISTS is safe).

-- Enable RLS on partitioned daily_snapshots (parent + all year partitions)
ALTER TABLE daily_snapshots            ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_snapshots_y2025      ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_snapshots_y2026      ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_snapshots_y2027      ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_snapshots_default    ENABLE ROW LEVEL SECURITY;

-- Enable RLS on partitioned documents (parent + all year partitions)
ALTER TABLE documents                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents_y2025            ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents_y2026            ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents_y2027            ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents_default          ENABLE ROW LEVEL SECURITY;

-- Recreate anon_read policies on partitioned parent tables
-- (policies on the parent are inherited by child partitions in PG 15+)
DROP POLICY IF EXISTS "anon_read" ON daily_snapshots;
CREATE POLICY "anon_read" ON daily_snapshots FOR SELECT TO anon USING (true);

DROP POLICY IF EXISTS "anon_read" ON documents;
CREATE POLICY "anon_read" ON documents FOR SELECT TO anon USING (true);
