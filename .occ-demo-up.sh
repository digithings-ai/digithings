set -e
export ZAMMAD_API_TOKEN="$(docker exec digi-zammad-mcp sh -c 'printf %s "$ZAMMAD_API_TOKEN"')"
export DIGICHAT_HOST_OCC_TOKEN="$(python3 -c 'import yaml,json,os;d=yaml.safe_load(open(os.path.expanduser("~/Code/digithings-wt-promo/docker-compose.override.yml")));print(json.loads(d["services"]["digichat"]["environment"]["DIGICHAT_EMBED_TENANTS"])["occ.digithings.ai"]["token"],end="")')"
export DIGI_TENANT_CORPUS_MAP="$(python3 $HOME/Code/digithings-wt-release-occ-chat/.occ-corpus.py < ~/Code/digithings-wt-release-occ-chat/infra/digichat-release/compose.profile-a-bundle.override.yml)"
[ -n "$ZAMMAD_API_TOKEN" ] && [ -n "$DIGICHAT_HOST_OCC_TOKEN" ] || { echo missing; exit 1; }
cd ~/Code/digithings-wt-promo
docker compose --profile digichat -f docker-compose.yml -f docker-compose.override.yml -f ~/Code/digithings-wt-release-occ-chat/.occ-demo.override.yml up -d --no-deps --no-build "$@"
if printf "%s\n" "$@" | grep -qx digichat; then sleep 5; got="$(docker exec digi-digichat sh -c 'printf %s "$DIGICHAT_HOST_OCC_TOKEN"')"; [ "$got" = "$DIGICHAT_HOST_OCC_TOKEN" ] && echo "OCC token OK (${#got} chars)" || { echo "OCC token MISSING/MISMATCH in container"; exit 2; }; fi
# digichat -f docker-compose.yml -f docker-compose.override.yml -f ~/Code/digithings-wt-release-occ-chat/.occ-demo.override.yml up -d --no-deps --no-build "$@"
