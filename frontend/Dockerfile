# syntax=docker/dockerfile:1

FROM node:24-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm,sharing=locked \
    npm ci --prefer-offline --no-audit

COPY . .

ARG VITE_DATA_SOURCE=api
ARG VITE_API_BASE_URL=
ARG VITE_DATASET_ID=nuscenes
ARG VITE_DATASET_NAME=nuScenes cloud dataset
ARG VITE_DATASET_FORMAT=nuScenes
ARG VITE_DATASET_VERSION=v1.0-trainval
ARG VITE_DATASET_DEFAULT_SPLIT=trainval-full
ARG VITE_AUTH_MODE=supabase
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY

ENV VITE_DATA_SOURCE=${VITE_DATA_SOURCE} \
    VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_DATASET_ID=${VITE_DATASET_ID} \
    VITE_DATASET_NAME=${VITE_DATASET_NAME} \
    VITE_DATASET_FORMAT=${VITE_DATASET_FORMAT} \
    VITE_DATASET_VERSION=${VITE_DATASET_VERSION} \
    VITE_DATASET_DEFAULT_SPLIT=${VITE_DATASET_DEFAULT_SPLIT} \
    VITE_AUTH_MODE=${VITE_AUTH_MODE} \
    VITE_SUPABASE_URL=${VITE_SUPABASE_URL} \
    VITE_SUPABASE_ANON_KEY=${VITE_SUPABASE_ANON_KEY}

RUN npm run build

FROM nginx:1.27-alpine AS production

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://localhost/healthz >/dev/null || exit 1
