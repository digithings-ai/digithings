set -e
export ZAMMAD_API_TOKEN="$(docker exec digi-zammad-mcp sh -c 'printf %s "$ZAMMAD_API_TOKEN"')"
export DIGICHAT_HOST_OCC_TOKEN="$(docker exec digi-digichat sh -c 'printf %s "$DIGICHAT_EMBED_TENANTS"' | python3 -c 'import json,sys;print(json.load(sys.stdin)["occ.digithings.ai"]["token"],end="")')"
export DIGI_TENANT_CORPUS_MAP="$(python3 $HOME/Code/digithings-wt-release-occ-chat/.occ-corpus.py < ~/Code/digithings-wt-release-occ-chat/infra/digichat-release/compose.profile-a-bundle.override.yml)"
[ -n "$ZAMMAD_API_TOKEN" ] && [ -n "$DIGICHAT_HOST_OCC_TOKEN" ] || { echo missing; exit 1; }
cd ~/Code/digithings-wt-promo
docker compose --profile digichat -f docker-compose.yml -f docker-compose.override.yml -f ~/Code/digithings-wt-release-occ-chat/.occ-demo.override.yml up -d --no-deps --no-build "$@"
