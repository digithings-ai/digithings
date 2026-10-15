# digichat — Next.js standalone.
# Build from the REPO ROOT (compose: context '.', dockerfile apps/digichat/Dockerfile):
# the root lockfile pins the install. @digithings/design, @digithings/ui and
# @digithings/digichat-ui come from tarballs (scripts/package_r5_image_inputs.py),
# not from a sibling-tree COPY. The only app tree copied is apps/digichat.
FROM node:22-alpine AS deps
WORKDIR /app
RUN apk add --no-cache libc6-compat
COPY package.json package-lock.json ./
COPY apps/digichat/package.json apps/digichat/
COPY image-packages/digichat/manifests/design/package.json packages/design/package.json
COPY image-packages/digichat/manifests/ui/package.json packages/ui/package.json
COPY image-packages/digichat/manifests/digichat-ui/package.json packages/digichat-ui/package.json
COPY image-packages/digichat/manifests/dashboard/package.json apps/dashboard/package.json
RUN npm ci --workspace apps/digichat --include-workspace-root

FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# /embed frame-ancestors are set at request time by src/proxy.ts from runtime
# DIGICHAT_EMBED_HOSTS and/or DIGICHAT_EMBED_TENANTS host keys.
# Do NOT pass DIGICHAT_EMBED_TENANTS as a build-arg (tokens in layer history).
# DIGICHAT_EMBED_HOSTS build-arg is unused for CSP after runtime proxy; omit it.
COPY --from=deps /app ./
COPY image-packages/digichat/npm/ /tmp/digi-npm/
# Unpack the published package trees over the manifests npm ci linked.
# Grammar moved into the package (WS1): chat-digichat.css ships with
# packages/ui, so no gallery COPY is needed anymore (#3717 closed).
RUN tar -xzf /tmp/digi-npm/digithings-design-*.tgz -C packages/design --strip-components=1 \
 && tar -xzf /tmp/digi-npm/digithings-ui-*.tgz -C packages/ui --strip-components=1 \
 && tar -xzf /tmp/digi-npm/digithings-digichat-ui-*.tgz -C packages/digichat-ui --strip-components=1
COPY apps/digichat ./apps/digichat
COPY tsconfig.base.json ./tsconfig.base.json
# BYOK provider pins are imported from the repo-root config (#5020).
COPY config/byok-providers.json ./config/byok-providers.json
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
# OCI image annotations: make the image self-describing so an immutable digest
# can be proven back to the commit that built it, without trusting a mutable tag.
# The publish lane passes DIGICHAT_REVISION=<full sha> and DIGICHAT_SOURCE_URL;
# a local `docker build` that omits them still builds (labels come out empty),
# which is why the binding check treats a missing revision as a failure for
# released images rather than for any image. See docs/ops/digichat-datatap-aca.md.
ARG DIGICHAT_REVISION=""
ARG DIGICHAT_SOURCE_URL="https://github.com/digithings-ai/digithings"
# D-R5-1. Account id is supplied by the operator at push time (H3).
ARG IMAGE_PUSH_REGISTRY=registry.cloudflare.com
ARG IMAGE_PUSH_REPOSITORY=digithings/digichat
LABEL org.digithings.image.registry="${IMAGE_PUSH_REGISTRY}" \
      org.digithings.image.repository="${IMAGE_PUSH_REPOSITORY}" \
      org.opencontainers.image.revision=$DIGICHAT_REVISION \
      org.opencontainers.image.version=$DIGICHAT_VERSION \
      org.opencontainers.image.source=$DIGICHAT_SOURCE_URL
USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
CMD ["node", "apps/digichat/scripts/trusted-proxy-server.mjs"]
