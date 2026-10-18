# Console image for the local stack (compose.yaml). Build context: the repository root
# (npm workspaces: one lockfile, packages/ui is source-only). Reproducible: base image
# pinned by digest, dependencies exactly from package-lock.json (npm ci).
# The API proxy target is fixed at build time (next.config.ts rewrites).
FROM node:24.13.1-bookworm-slim@sha256:a81a03dd965b4052269a57fac857004022b522a4bf06e7a739e25e18bce45af2 AS build
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /src
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/
COPY apps/site/package.json apps/site/
COPY packages/ui/package.json packages/ui/
RUN npm ci --workspace web --no-audit --no-fund
COPY packages/ui packages/ui
COPY apps/web apps/web
ARG AUTORESILIENCE_API_URL=http://api:8000
ENV AUTORESILIENCE_API_URL=${AUTORESILIENCE_API_URL} AUTORESILIENCE_STANDALONE=1
RUN npm run build --workspace web

FROM node:24.13.1-bookworm-slim@sha256:a81a03dd965b4052269a57fac857004022b522a4bf06e7a739e25e18bce45af2
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /app
COPY --from=build /src/apps/web/.next/standalone ./
COPY --from=build /src/apps/web/.next/static ./apps/web/.next/static
COPY --from=build /src/apps/web/public ./apps/web/public
USER node
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
