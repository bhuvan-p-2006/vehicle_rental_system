# syntax=docker/dockerfile:1.7
# Multi-stage build (SPEC §13.6). Node is a build-time tool only; the runtime
# image is nginx serving static assets.

# ---------------------------------------------------------------------------
# Stage 1: build
# ---------------------------------------------------------------------------
FROM node:20-alpine AS build

WORKDIR /app

# VITE_API_URL is inlined at build time, so it must be declared before npm run build.
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=$VITE_API_URL

# `npm ci` installs exactly what package-lock.json pins (SPEC §13.7).
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

# nginx:alpine ships an unprivileged user; drop privileges to it.
RUN touch /var/run/nginx.pid && chown -R nginx:nginx /var/run/nginx.pid /var/cache/nginx
USER nginx

EXPOSE 80

# Healthcheck uses 127.0.0.1 rather than `localhost`: inside the container
# `localhost` resolves to ::1 first, but nginx listens on IPv4 only.
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]