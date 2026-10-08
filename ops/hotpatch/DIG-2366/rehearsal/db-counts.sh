#!/bin/bash
# DIG-2366 rehearsal — direct database evidence for one issue.
#
# usage: db-counts.sh <pg_port> <issue_id>
#
# The API list endpoint is itself part of the patched surface, so the row counts
# are read straight out of postgres as a second, independent witness.

set -euo pipefail

PORT="$1"
ISSUE="$2"
export PGPASSWORD=paperclip

q() {
  psql -h 127.0.0.1 -p "$PORT" -U paperclip -d paperclip -At -c "$1" | tr -d ' \n'
}

printf 'db_issue_documents_rows=%s\n' "$(q "select count(*) from issue_documents where issue_id = '${ISSUE}';")"
printf 'db_documents_rows=%s\n'          "$(q "select count(*) from documents d join issue_documents l on l.document_id = d.id where l.issue_id = '${ISSUE}';")"
printf 'db_document_keys=%s\n'           "$(q "select string_agg(l.key, ',' order by l.key) from issue_documents l where l.issue_id = '${ISSUE}';")"
printf 'db_document_ids=%s\n'           "$(q "select string_agg(l.document_id, ',' order by l.key) from issue_documents l where l.issue_id = '${ISSUE}';")"
printf 'db_issue_title=%s\n'            "$(q "select title from issues where id = '${ISSUE}';")"
