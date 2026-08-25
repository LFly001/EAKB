# ============================================================
# EAKB 前端生产镜像 (Phase 8) — 多阶段构建
# 阶段 1: Node 20 构建静态资源
# 阶段 2: Nginx 托管 + 反向代理后端 (SSE 透传)
# ============================================================

# ---- 构建阶段 ----
FROM node:20-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# API 地址在构建时注入 (同源部署: nginx 同域反代 /api/v1)
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_SSE_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_SSE_BASE_URL=${VITE_SSE_BASE_URL}

RUN npm run build

# ---- 运行阶段 ----
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
