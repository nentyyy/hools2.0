FROM node:22-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

COPY shared /shared
COPY frontend ./

ARG VITE_API_URL=""
ARG VITE_TON_MANIFEST_URL=""
ENV VITE_API_URL=$VITE_API_URL \
    VITE_TON_MANIFEST_URL=$VITE_TON_MANIFEST_URL

RUN npm run build

FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
