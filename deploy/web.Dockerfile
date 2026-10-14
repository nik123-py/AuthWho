# Builds the SDK, the demo app and the admin dashboard, then serves them with nginx.
FROM node:24-bookworm-slim AS build
WORKDIR /src
COPY package.json package-lock.json ./
COPY sdk/package.json sdk/package.json
COPY dashboard/package.json dashboard/package.json
COPY demo_app/frontend/package.json demo_app/frontend/package.json
RUN npm ci --no-audit --no-fund
COPY sdk sdk
COPY dashboard dashboard
COPY demo_app/frontend demo_app/frontend
RUN npm run build -w sdk \
    && npm run build -w demo_app/frontend \
    && npm exec -w dashboard -- vite build --base=/admin/

FROM nginx:1.27-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/demo_app/frontend/dist /usr/share/nginx/html/app
COPY --from=build /src/dashboard/dist /usr/share/nginx/html/admin
EXPOSE 80
