# syntax=docker/dockerfile:1

FROM node:22-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# Vite inlines import.meta.env at build time, so this is an ARG, not a runtime
# env var. Empty means the app uses the relative /api/v1 path nginx proxies.
ARG VITE_API_URL=""
ARG VITE_BUILD_ID=dev
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_BUILD_ID=$VITE_BUILD_ID
RUN npm run build


FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
