-- Compare latest dates: Activity ledger vs positions vs NAV (run in Supabase SQL editor).
SELECT
  (SELECT max(date) FROM position_events) AS max_position_events_date,
  (SELECT max(date) FROM positions) AS max_positions_date,
  (SELECT max(date) FROM nav_history) AS max_nav_history_date,
  (SELECT max(date) FROM daily_snapshots) AS max_daily_snapshots_date;
