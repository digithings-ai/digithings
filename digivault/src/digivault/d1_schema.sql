-- digivault note store for one corpus. Applied by scripts/d1_sync.py --init.
CREATE TABLE IF NOT EXISTS notes (
  vault_path    TEXT PRIMARY KEY,          -- canonical: NO .md suffix
  title         TEXT NOT NULL DEFAULT '',
  note_type     TEXT NOT NULL DEFAULT '',
  summary       TEXT NOT NULL DEFAULT '',
  body          TEXT NOT NULL DEFAULT '',
  frontmatter   TEXT NOT NULL DEFAULT '{}',  -- JSON object
  tags          TEXT NOT NULL DEFAULT '[]',  -- JSON array
  wikilinks     TEXT NOT NULL DEFAULT '[]',  -- JSON array
  parent_doc    TEXT,
  segment_index INTEGER,
  updated_at    TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS notes_parent ON notes(parent_doc, segment_index);

-- External-content FTS5: the index references notes rather than copying its text.
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts
  USING fts5(title, summary, body, content='notes', content_rowid='rowid');
