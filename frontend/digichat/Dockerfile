# digichat — Next.js standalone.
# Build from the REPO ROOT (compose: context '.', dockerfile frontend/digichat/Dockerfile):
# the app is an npm workspace member whose lockfile lives at the repo root and whose
# private @digithings/design dependency only resolves through the workspace link.
FROM node:22-alpine AS deps
WORKDIR /app
RUN apk add --no-cache libc6-compat
COPY package.json package-lock.json ./
COPY frontend/digichat/package.json frontend/digichat/
COPY frontend/digichat-ui/package.json frontend/digichat-ui/
COPY frontend/digiweb/design/package.json frontend/digiweb/design/
COPY frontend/digiweb/web/package.json frontend/digiweb/web/
COPY frontend/dashboard/package.json frontend/dashboard/
RUN npm ci --workspace frontend/digichat --include-workspace-root

FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# /embed frame-ancestors are set at request time by src/proxy.ts from runtime
# DIGICHAT_EMBED_HOSTS and/or DIGICHAT_EMBED_TENANTS host keys.
# Do NOT pass DIGICHAT_EMBED_TENANTS as a build-arg (tokens in layer history).
# DIGICHAT_EMBED_HOSTS build-arg is unused for CSP after runtime proxy; omit it.
COPY --from=deps /app ./
COPY frontend/digiweb/design ./frontend/digiweb/design
COPY frontend/digiweb/web ./frontend/digiweb/web
COPY frontend/digichat-ui ./frontend/digichat-ui
COPY frontend/digichat ./frontend/digichat
RUN npm run build --workspace frontend/digichat

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
RUN apk add --no-cache curl
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
# Workspace standalone output mirrors the monorepo: server.js lives at
# frontend/digichat/server.js inside the standalone tree.
COPY --from=builder --chown=nextjs:nodejs /app/frontend/digichat/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/frontend/digichat/.next/static ./frontend/digichat/.next/static
COPY --from=builder --chown=nextjs:nodejs /app/frontend/digichat/public ./frontend/digichat/public
COPY --from=builder --chown=nextjs:nodejs /app/frontend/digichat/scripts/trusted-proxy-server.mjs ./frontend/digichat/scripts/trusted-proxy-server.mjs
# Drizzle migrations: the standalone server.js chdir()s to its own directory,
# so runMigrate() resolves process.cwd()/drizzle = frontend/digichat/drizzle.
# Compose sets DIGICHAT_AUTO_MIGRATE=1, so the folder MUST ship in the image.
COPY --from=builder --chown=nextjs:nodejs /app/frontend/digichat/drizzle ./frontend/digichat/drizzle
USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
CMD ["node", "frontend/digichat/scripts/trusted-proxy-server.mjs"]
