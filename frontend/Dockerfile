FROM node:20-alpine AS builder

WORKDIR /app

ARG VITE_PASSWORD_ENCRYPTION_KEY
ENV VITE_PASSWORD_ENCRYPTION_KEY=${VITE_PASSWORD_ENCRYPTION_KEY}

COPY package.json pnpm-lock.yaml ./
RUN npm install -g pnpm@9.15.9 \
    && pnpm config set registry https://registry.npmmirror.com \
    && HUSKY=0 pnpm install --frozen-lockfile

COPY . .
RUN pnpm run build \
    && pnpm run build:share

FROM nginx:1.27-alpine

ENV BACKEND_UPSTREAM=http://platform-backend:8000

COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html/dist
COPY --from=builder /app/dist-share /usr/share/nginx/html/dist-share

EXPOSE 80 3840
