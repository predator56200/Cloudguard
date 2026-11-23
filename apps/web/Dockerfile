# =============================================================================
# apps/web — Next.js 15, multi-stage
# =============================================================================
# Build context is apps/web (NOT the repo root), because the frontend shares no source with
# the Python packages. Smaller context = faster builds.
#
# The prod stage is where the interesting work happens: it takes a ~1.2GB build environment
# and produces a ~150MB runtime image, using Next's `output: 'standalone'` (next.config.ts).
# =============================================================================

# --- base --------------------------------------------------------------------
FROM node:22-alpine AS base
WORKDIR /app
# Alpine is fine for Node (unlike Python — see apps/api/Dockerfile for why musl breaks there).
# libc6-compat covers the few native modules that still expect glibc symbols.
# `apk upgrade` pulls in Alpine security fixes released after the base image was built.
RUN apk upgrade --no-cache && apk add --no-cache libc6-compat

# --- deps --------------------------------------------------------------------
FROM base AS deps
# ONLY the lockfiles. This layer is cached and rebuilt only when dependencies change — not on
# every source edit. Copying source first would reinstall node_modules on every commit,
# turning a 10-second rebuild into three minutes.
COPY package.json package-lock.json* ./
# `npm ci` (not `npm install`): installs EXACTLY the lockfile, fails if package.json and the
# lock disagree, and never silently upgrades a transitive dependency mid-build. A build that
# can pull a different dependency tree than the one you tested is a supply-chain risk, and we
# are a security company.
RUN npm ci

# --- dev ---------------------------------------------------------------------
FROM base AS dev
COPY --from=deps /app/node_modules ./node_modules
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]

# --- builder -----------------------------------------------------------------
FROM base AS builder
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# --- prod --------------------------------------------------------------------
FROM base AS prod
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Non-root, same reasoning as the Python images: root inside a container plus any escape
# primitive is root on a host shared with other workloads.
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

# The runtime is `node server.js`: it never needs npm, npx, yarn or corepack. The base image
# ships them anyway, and npm's own bundled dependencies (sigstore, pacote, brace-expansion...)
# were most of Trivy's findings against this image. Remove the package managers entirely.
RUN rm -rf /usr/local/lib/node_modules \
    /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
    /usr/local/bin/yarn /usr/local/bin/yarnpkg /opt/yarn-*

# `standalone` contains the server plus ONLY the node_modules actually reached by the code —
# Next traces the import graph. This is why the runtime image is ~150MB instead of ~1.2GB.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
