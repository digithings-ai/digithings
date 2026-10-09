#!/usr/bin/env node
// Local fixture standing in for `https://digithings.ai/api/embed/tenant-config`.
//
// It exists to answer one question that production cannot yet answer: can
// scripts/verify_occ_invite_key.sh ever report the closure bar as met? Check 2
// ("correct key, no origin" -> slug=occ) is the bar for closing DIG-1381, and
// because no rollout has ever run, nobody has ever watched it pass.
//
// It re-implements hostTenantAuthorized from apps/digichat/src/lib/embed-chat-tenant.ts
// line-for-line, and reads FIRST_PARTY_EMBED_HOSTS off disk rather than copying
// it, so the fixture cannot drift from the real allowlist: delete the
// occ.digithings.ai entry in the real source and this fixture stops honouring it.
//
// Bounded assumption, stated rather than hidden: normalizeEmbedHost lives in
// @/lib/embed-tenants behind a build alias this script cannot import, so host
// normalisation is `new URL(h).host`. Every host verify_occ_invite_key.sh sends
// is a full https:// origin, for which that is exact. assertAllowlistParsed is
// the positive control proving the off-disk read actually happened.

import { readFileSync } from "node:fs";
import { createServer } from "node:http";

const ALLOWLIST_SRC = "apps/digichat/src/lib/embed-first-party.ts";
const OCC_TOKEN = process.env.FIXTURE_OCC_TOKEN ?? "";
const PORT = Number(process.env.FIXTURE_PORT ?? 8787);

function firstPartyHosts() {
  const src = readFileSync(ALLOWLIST_SRC, "utf8");
  const block = src.match(
    /FIRST_PARTY_EMBED_HOSTS[^=]*=\s*new Set\(\[([\s\S]*?)\]\)/,
  );
  if (!block) throw new Error(`could not read FIRST_PARTY_EMBED_HOSTS from ${ALLOWLIST_SRC}`);
  return new Set(
    [...block[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]),
  );
}

const FIRST_PARTY = firstPartyHosts();
// Simulates Act B2 without editing the real source: drop a host from the set we
// just read. Used to prove the post-B2 expectations without a deploy.
const DROP = process.env.FIXTURE_DROP_HOST ?? "";
if (DROP) {
  if (!FIRST_PARTY.delete(DROP)) throw new Error(`FIXTURE_DROP_HOST=${DROP} was not on the allowlist`);
  console.error(`fixture: simulated Act B2 by dropping ${DROP}`);
}
// Positive control: an empty or mis-parsed allowlist would make every probe
// refuse and look like a passing fixture.
if (FIRST_PARTY.size === 0) throw new Error("allowlist parsed as EMPTY — extraction is broken");
if (!FIRST_PARTY.has("digithings.ai")) throw new Error("positive control failed: digithings.ai missing");

// apps/digichat/src/lib/embed-chat-tenant.ts, verbatim.
function tokenMatches(required, token) {
  const expected = required.trim();
  const presented = token?.trim();
  return Boolean(expected && presented && presented === expected);
}
function isFirstPartyEmbedHost(host) {
  if (!host) return false;
  let normalized = "";
  try {
    normalized = new URL(host.includes("://") ? host : `https://${host}`).host;
  } catch {
    return false;
  }
  return FIRST_PARTY.has(normalized);
}
function hostTenantAuthorized(tenantToken, token, host, originHost) {
  if (tokenMatches(tenantToken, token)) return true;
  return isFirstPartyEmbedHost(host) && isFirstPartyEmbedHost(originHost);
}

const server = createServer((req, res) => {
  const h = req.headers;
  const originHost = h.origin ? new URL(h.origin).host : null;
  const granted = hostTenantAuthorized(
    OCC_TOKEN,
    h["x-embed-token"] ?? null,
    h["x-embed-host"] ?? null,
    originHost,
  );
  const body = JSON.stringify(
    granted
      ? { slug: "occ", gateMode: "ungated", title: "OCC help assistant" }
      : { slug: "embed", gateMode: "gated" },
  );
  res.writeHead(200, { "content-type": "application/json" });
  res.end(body);
});

server.listen(PORT, "127.0.0.1", () => {
  console.error(
    `fixture listening on http://127.0.0.1:${PORT} allowlist=${[...FIRST_PARTY].join(",")}`,
  );
});
