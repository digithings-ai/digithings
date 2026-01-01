-- SQLite equivalents of the row-level Postgres trigger functions.
--
-- Covers every non-reject trigger binding in digiquant/supabase/migrations:
--   trigger_set_updated_at         -> daily_snapshots, positions, theses,
--                                    portfolio_metrics, workspaces,
--                                    notification_prefs
--   set_instruments_updated_at     -> instruments
--   knowledge_notes_set_updated_at -> knowledge_notes
--   ensure_position_instrument     -> positions (upsert into instruments)
--   reject_..._base_mismatch       -> olympus_evidence_bundle_amendments
--      (the one row guard that is NOT a reject_*_mutation; the 19
--      reject_*_mutation guards live in d1_reject_guards.sql)
--
-- handle_new_auth_user_workspace has no trigger here: D1 carries no auth
-- schema, so signup provisioning is Worker code
-- (d1_functions.handle_new_auth_user_workspace), not a trigger.
--
-- SQLite cannot assign NEW.col in a BEFORE trigger (Postgres can), so the
-- updated_at maintenance uses AFTER triggers with WHEN guards: the INSERT
-- arm stamps only rows inserted without a timestamp, and the UPDATE arm
-- stamps only rows whose timestamp the writer left untouched. The WHEN
-- guard is what stops the trigger recursing into itself.

-- daily_snapshots -------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_d1_daily_snapshots_ins_updated_at
AFTER INSERT ON daily_snapshots FOR EACH ROW
WHEN NEW.updated_at IS NULL
BEGIN
    UPDATE daily_snapshots
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE rowid = NEW.rowid;
END;

CREATE TRIGGER IF NOT EXISTS trg_d1_daily_snapshots_upd_updated_at
AFTER UPDATE ON daily_snapshots FOR EACH ROW
WHEN NEW.updated_at IS OLD.updated_at
BEGIN
    UPDATE daily_snapshots
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE rowid = NEW.rowid;
END;

-- positions -------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_d1_positions_ins_updated_at
AFTER INSERT ON positions FOR EACH ROW
WHEN NEW.updated_at IS NULL
BEGIN
    UPDATE positions
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE rowid = NEW.rowid;
END;

CREATE TRIGGER IF NOT EXISTS trg_d1_positions_upd_updated_at
AFTER UPDATE ON positions FOR EACH ROW
WHEN NEW.updated_at IS OLD.updated_at
BEGIN
    UPDATE positions
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE rowid = NEW.rowid;
END;

-- theses ----------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_d1_theses_ins_updated_at
AFTER INSERT ON theses FOR EACH ROW
WHEN NEW.updated_at IS NULL
BEGIN
    UPDATE theses
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE rowid = NEW.rowid;
END;

CREATE TRIGGER IF NOT EXISTS trg_d1_theses_upd_updated_at
AFTER UPDATE ON theses FOR EACH ROW
WHEN NEW.updated_at IS OLD.updated_at
BEGIN
    UPDATE theses
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE rowid = NEW.rowid;
END;

-- portfolio_metrics ------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_d1_portfolio_metrics_ins_updated_at
AFTER INSERT ON portfolio_metrics FOR EACH ROW
WHEN NEW.updated_at IS NULL
BEGIN
    UPDATE portfolio_metrics
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE rowid = NEW.rowid;
END;

CREATE TRIGGER IF NOT EXISTS trg_d1_portfolio_metrics_upd_updated_at
AFTER UPDATE ON portfolio_metrics FOR EACH ROW
WHEN NEW.updated_at IS OLD.updated_at
BEGIN
    UPDATE portfolio_metrics
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE rowid = NEW.rowid;
END;

-- workspaces -------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_d1_workspaces_ins_updated_at
AFTER INSERT ON workspaces FOR EACH ROW
WHEN NEW.updated_at IS NULL
BEGIN
    UPDATE workspaces
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE rowid = NEW.rowid;
END;

CREATE TRIGGER IF NOT EXISTS trg_d1_workspaces_upd_updated_at
AFTER UPDATE ON workspaces FOR EACH ROW
WHEN NEW.updated_at IS OLD.updated_at
BEGIN
    UPDATE workspaces
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE rowid = NEW.rowid;
END;

-- notification_prefs ------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_d1_notification_prefs_ins_updated_at
AFTER INSERT ON notification_prefs FOR EACH ROW
WHEN NEW.updated_at IS NULL
BEGIN
    UPDATE notification_prefs
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE rowid = NEW.rowid;
END;

CREATE TRIGGER IF NOT EXISTS trg_d1_notification_prefs_upd_updated_at
AFTER UPDATE ON notification_prefs FOR EACH ROW
WHEN NEW.updated_at IS OLD.updated_at
BEGIN
    UPDATE notification_prefs
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE rowid = NEW.rowid;
END;

-- instruments --------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_d1_instruments_ins_updated_at
AFTER INSERT ON instruments FOR EACH ROW
WHEN NEW.updated_at IS NULL
BEGIN
    UPDATE instruments
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE rowid = NEW.rowid;
END;

CREATE TRIGGER IF NOT EXISTS trg_d1_instruments_upd_updated_at
AFTER UPDATE ON instruments FOR EACH ROW
WHEN NEW.updated_at IS OLD.updated_at
BEGIN
    UPDATE instruments
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE rowid = NEW.rowid;
END;

-- knowledge_notes ------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_d1_knowledge_notes_ins_updated_at
AFTER INSERT ON knowledge_notes FOR EACH ROW
WHEN NEW.updated_at IS NULL
BEGIN
    UPDATE knowledge_notes
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE rowid = NEW.rowid;
END;

CREATE TRIGGER IF NOT EXISTS trg_d1_knowledge_notes_upd_updated_at
AFTER UPDATE ON knowledge_notes FOR EACH ROW
WHEN NEW.updated_at IS OLD.updated_at
BEGIN
    UPDATE knowledge_notes
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE rowid = NEW.rowid;
END;

-- ensure_position_instrument: a new position resolves its instrument row,
-- creating an unresolved placeholder when the ticker is unknown.
-- (Postgres: BEFORE INSERT ... ON CONFLICT (ticker) DO NOTHING.)
CREATE TRIGGER IF NOT EXISTS trg_d1_positions_ensure_instrument
BEFORE INSERT ON positions FOR EACH ROW
BEGIN
    INSERT OR IGNORE INTO instruments (
        ticker, official_name, instrument_type, asset_class, category,
        provider, provider_metadata, source_updated_at
    ) VALUES (
        upper(trim(NEW.ticker)),
        CASE WHEN upper(trim(NEW.ticker)) = 'CASH'
             THEN 'Cash' ELSE upper(trim(NEW.ticker)) END,
        CASE WHEN upper(trim(NEW.ticker)) = 'CASH'
             THEN 'CASH' ELSE NULL END,
        CASE WHEN upper(trim(NEW.ticker)) = 'CASH'
             THEN 'CASH' ELSE 'UNKNOWN' END,
        CASE WHEN upper(trim(NEW.ticker)) = 'CASH'
             THEN 'cash' ELSE 'unknown' END,
        'position-trigger',
        '{"resolution":"unresolved"}',
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    );
END;

-- Amendment base-match guard (091): an amendment must point at the same base
-- bundle as its missing-fact request. Missing request reads as a FK breach
-- (Postgres ERRCODE 23503); a cross-linked base reads as a check breach
-- (Postgres ERRCODE 23514).
CREATE TRIGGER IF NOT EXISTS trg_d1_amendment_base_match_ins
BEFORE INSERT ON olympus_evidence_bundle_amendments FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM olympus_missing_fact_requests r
     WHERE r.request_id = NEW.missing_fact_request_id
)
BEGIN
    SELECT RAISE(ABORT,
        'missing-fact request not found for amendment (fk breach)');
END;

CREATE TRIGGER IF NOT EXISTS trg_d1_amendment_base_match_upd
BEFORE UPDATE ON olympus_evidence_bundle_amendments FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM olympus_missing_fact_requests r
     WHERE r.request_id = NEW.missing_fact_request_id
)
BEGIN
    SELECT RAISE(ABORT,
        'missing-fact request not found for amendment (fk breach)');
END;

CREATE TRIGGER IF NOT EXISTS trg_d1_amendment_base_mismatch_ins
BEFORE INSERT ON olympus_evidence_bundle_amendments FOR EACH ROW
WHEN EXISTS (
    SELECT 1 FROM olympus_missing_fact_requests r
     WHERE r.request_id = NEW.missing_fact_request_id
       AND r.base_bundle_id IS NOT NEW.base_bundle_id
)
BEGIN
    SELECT RAISE(ABORT,
        'amendment base_bundle_id must match missing-fact request base');
END;

CREATE TRIGGER IF NOT EXISTS trg_d1_amendment_base_mismatch_upd
BEFORE UPDATE ON olympus_evidence_bundle_amendments FOR EACH ROW
WHEN EXISTS (
    SELECT 1 FROM olympus_missing_fact_requests r
     WHERE r.request_id = NEW.missing_fact_request_id
       AND r.base_bundle_id IS NOT NEW.base_bundle_id
)
BEGIN
    SELECT RAISE(ABORT,
        'amendment base_bundle_id must match missing-fact request base');
END;
