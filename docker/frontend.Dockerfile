FROM node:20-alpine AS base

WORKDIR /app

RUN corepack enable

# Copy lockfile if present so reproducible builds can use it; tolerate its
# absence on a fresh checkout (commit 1 ships before `make install`).
COPY frontend/package.json ./
COPY frontend/pnpm-lock.yaml* ./
RUN if [ -f pnpm-lock.yaml ]; then pnpm install --frozen-lockfile; else pnpm install; fi

COPY frontend/ ./

EXPOSE 3000

CMD ["pnpm", "dev"]
