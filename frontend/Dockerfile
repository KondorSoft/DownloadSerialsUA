FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine

ENV BACKEND_URL=http://backend:8765 \
    KADR_APP_TOKEN=kadr-local-token \
    NGINX_ENVSUBST_FILTER=^(BACKEND_URL|KADR_APP_TOKEN)$

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 80
