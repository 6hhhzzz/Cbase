# KES Frontend Dockerfile — 多阶段构建
# 阶段 1: Node 构建
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# 阶段 2: Nginx 静态服务
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
# 自定义 Nginx 配置 — SPA 路由 + API 代理
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
  CMD wget -qO- http://localhost/ 2>/dev/null || exit 1
