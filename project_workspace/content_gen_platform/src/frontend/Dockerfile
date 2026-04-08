# Pin builder to amd64: npm/node crash under QEMU arm64 emulation (SIGILL).
# The build output (dist/) is pure JS/CSS — architecture-independent.
FROM --platform=linux/amd64 node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# Production stage — serve via Nginx
FROM nginx:1.25-alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# Override default nginx config to enable SPA routing
RUN echo 'server { \
    listen 80; \
    root /usr/share/nginx/html; \
    index index.html; \
    location / { try_files $uri $uri/ /index.html; } \
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff2?)$ { \
        expires 1y; add_header Cache-Control "public, immutable"; \
    } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80
