# digichat — Next.js standalone.
# Build from the REPO ROOT (compose: context '.', dockerfile apps/digichat/Dockerfile):
# the app is an npm workspace member whose lockfile lives at the repo root and whose
# private @digithings/design dependency only resolves through the workspace link.
FROM node:22-alpine AS deps
WORKDIR /app
RUN apk add --no-cache libc6-compat
COPY package.json package-lock.json ./
COPY apps/digichat/package.json apps/digichat/
COPY packages/digichat-ui/package.json packages/digichat-ui/
COPY packages/design/package.json packages/design/
COPY packages/ui/package.json packages/ui/
COPY apps/dashboard/package.json apps/dashboard/
RUN npm ci --workspace apps/digichat --include-workspace-root

FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# /embed frame-ancestors are set at request time by src/proxy.ts from runtime
# DIGICHAT_EMBED_HOSTS and/or DIGICHAT_EMBED_TENANTS host keys.
# Do NOT pass DIGICHAT_EMBED_TENANTS as a build-arg (tokens in layer history).
# DIGICHAT_EMBED_HOSTS build-arg is unused for CSP after runtime proxy; omit it.
COPY --from=deps /app ./
COPY packages/design ./packages/design
COPY packages/ui ./packages/ui
# Grammar moved into the package (WS1): chat-digichat.css ships with
# packages/ui, so no gallery COPY is needed anymore (#3717 closed).
COPY packages/digichat-ui ./packages/digichat-ui
COPY apps/digichat ./apps/digichat
# Same bake as Dockerfile.digichat-cloudflare: health version matches package.json.
ARG DIGICHAT_VERSION
RUN VERSION="${DIGICHAT_VERSION:-$(node -p "require('./apps/digichat/package.json').version")}" \
 && printf '%s' "$VERSION" > /tmp/digichat-version \
 && DIGICHAT_VERSION="$VERSION" npm run build --workspace apps/digichat

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
RUN apk add --no-cache curl
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
# Workspace standalone output mirrors the monorepo: server.js lives at
# apps/digichat/server.js inside the standalone tree.
COPY --from=builder --chown=nextjs:nodejs /app/apps/digichat/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/digichat/.next/static ./apps/digichat/.next/static
COPY --from=builder --chown=nextjs:nodejs /app/apps/digichat/public ./apps/digichat/public
COPY --from=builder --chown=nextjs:nodejs /app/apps/digichat/scripts/trusted-proxy-server.mjs ./apps/digichat/scripts/trusted-proxy-server.mjs
# Drizzle migrations: the standalone server.js chdir()s to its own directory,
# so runMigrate() resolves process.cwd()/drizzle = apps/digichat/drizzle.
# Compose sets DIGICHAT_AUTO_MIGRATE=1, so the folder MUST ship in the image.
COPY --from=builder --chown=nextjs:nodejs /app/apps/digichat/drizzle ./apps/digichat/drizzle
# Operator deploy YAML examples (DIGICHAT_CONFIG_PATH=/app/config/examples/skins/<id>.yaml)
COPY --from=builder --chown=nextjs:nodejs /app/apps/digichat/config /app/config
COPY --from=builder /tmp/digichat-version /etc/digichat-version
ARG DIGICHAT_VERSION
ENV DIGICHAT_VERSION=$DIGICHAT_VERSION
USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
CMD ["node", "apps/digichat/scripts/trusted-proxy-server.mjs"]
