# syntax=docker/dockerfile:1
# Build from the REPO ROOT (pnpm workspace):  docker build -f apps/web/Dockerfile .
# Plain `next start` (not `output: "standalone"`): next.config.ts is not switched to standalone.
ARG NODE_VERSION=22

FROM node:${NODE_VERSION}-alpine AS base
ENV PNPM_HOME=/pnpm CI=1 NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /app

FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile --filter @setu/web...

FROM deps AS build
# NEXT_PUBLIC_* are inlined at build time; AGENT_URL is baked into the /api rewrite at build time.
ARG NEXT_PUBLIC_API_BASE=/api
ARG NEXT_PUBLIC_AGENT_URL
ARG NEXT_PUBLIC_SITE_URL
ARG NEXT_PUBLIC_JUDGE_EMAIL
ARG NEXT_PUBLIC_JUDGE_NOTE
ARG NEXT_PUBLIC_REPO_URL
ARG NEXT_PUBLIC_VIDEO_URL
ARG NEXT_PUBLIC_STATUS_URL
ARG GIT_SHA
ARG BUILD_TIME
ARG AGENT_URL=http://agent:8000
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE \
    NEXT_PUBLIC_AGENT_URL=$NEXT_PUBLIC_AGENT_URL \
    NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL \
    NEXT_PUBLIC_JUDGE_EMAIL=$NEXT_PUBLIC_JUDGE_EMAIL \
    NEXT_PUBLIC_JUDGE_NOTE=$NEXT_PUBLIC_JUDGE_NOTE \
    NEXT_PUBLIC_REPO_URL=$NEXT_PUBLIC_REPO_URL \
    NEXT_PUBLIC_VIDEO_URL=$NEXT_PUBLIC_VIDEO_URL \
    NEXT_PUBLIC_STATUS_URL=$NEXT_PUBLIC_STATUS_URL \
    NEXT_PUBLIC_GIT_SHA=$GIT_SHA \
    NEXT_PUBLIC_BUILD_TIME=$BUILD_TIME \
    AGENT_URL=$AGENT_URL
COPY apps/web apps/web
# Unset empty NEXT_PUBLIC_* (unset build args become ""), so `?? default` fallbacks in the app still apply.
RUN for v in $(env | grep -E '^NEXT_PUBLIC_[A-Z_]+=$' | cut -d= -f1); do unset "$v"; done; pnpm --dir apps/web build

FROM base AS runtime
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000
RUN addgroup -S setu && adduser -S setu -G setu
COPY --from=build --chown=setu:setu /app/package.json /app/pnpm-workspace.yaml ./
COPY --from=build --chown=setu:setu /app/node_modules node_modules
COPY --from=build --chown=setu:setu /app/apps/web/package.json apps/web/package.json
COPY --from=build --chown=setu:setu /app/apps/web/node_modules apps/web/node_modules
COPY --from=build --chown=setu:setu /app/apps/web/.next apps/web/.next
COPY --from=build --chown=setu:setu /app/apps/web/public apps/web/public
COPY --from=build --chown=setu:setu /app/apps/web/next.config.ts apps/web/next.config.ts
USER setu
WORKDIR /app/apps/web
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/robots.txt').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "node_modules/next/dist/bin/next", "start", "-H", "0.0.0.0"]
