# DigiChat — Next.js standalone.
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
COPY frontend/olympus/package.json frontend/olympus/
RUN npm ci --workspace frontend/digichat --include-workspace-root

FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# next.config.ts imports security-headers.ts, which reads DIGICHAT_EMBED_HOSTS
# once at import time to compute the embed CSP frame-ancestors list — Next.js
# evaluates this during `next build` and bakes it into the routes manifest, so
# it must be passed as a build arg, not just a runtime container env var.
# Deliberately DIGICHAT_EMBED_HOSTS (plain hostnames), not DIGICHAT_EMBED_TENANTS
# (which also carries each tenant's secret token) — build-args persist in image
# layer history and cloud-build logs (az acr build etc.), and the CSP computation
# never reads the token anyway. DIGICHAT_EMBED_TENANTS stays runtime-only.
ARG DIGICHAT_EMBED_HOSTS=""
ENV DIGICHAT_EMBED_HOSTS=$DIGICHAT_EMBED_HOSTS
COPY --from=deps /app ./
COPY frontend/digiweb/design ./frontend/digiweb/design
COPY frontend/digichat-ui ./frontend/digichat-ui
COPY frontend/digichat ./frontend/digichat
# package-lock.json is macOS-generated; Linux optional natives are not locked
# (see .github/workflows/test-digichat.yml, which needs the -gnu equivalents
# on its own non-Alpine runner — this image is musl/Alpine, hence -musl here).
RUN npm install \
      @rolldown/binding-linux-x64-musl@1.0.0-rc.16 \
      lightningcss-linux-x64-musl@1.32.0 \
      @tailwindcss/oxide-linux-x64-musl@4.2.2 \
      --no-save --no-audit --no-fund
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
# Drizzle migrations: the standalone server.js chdir()s to its own directory,
# so runMigrate() resolves process.cwd()/drizzle = frontend/digichat/drizzle.
# Compose sets DIGICHAT_AUTO_MIGRATE=1, so the folder MUST ship in the image.
COPY --from=builder --chown=nextjs:nodejs /app/frontend/digichat/drizzle ./frontend/digichat/drizzle
USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
CMD ["node", "frontend/digichat/server.js"]
