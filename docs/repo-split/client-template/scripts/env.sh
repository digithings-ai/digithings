# Source me: paths and non-secret env for running this client against an R0 checkout.
CLIENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export CLIENT_DIR
if [ -f "$CLIENT_DIR/.link" ]; then
  DIGITHINGS_DIR="$(cat "$CLIENT_DIR/.link")"   # written by `make link`
fi
export DIGITHINGS_DIR="${DIGITHINGS_DIR:-$CLIENT_DIR/../digithings}"
export DIGI_TENANT_CORPUS_MAP="$(cat "$CLIENT_DIR/tenant/corpus-map.json")"
export DIGIGRAPH_WEB_SEARCH_SITES_DIR="$CLIENT_DIR/tools/site-graph"
export DIGISEARCH_PAGE_CORPUS_DIR="$CLIENT_DIR/corpus"
lock() { sed -n "s/^$1=//p" "$CLIENT_DIR/digithings.lock"; }
