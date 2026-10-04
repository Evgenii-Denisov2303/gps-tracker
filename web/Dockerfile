FROM node:22-alpine AS vendor
WORKDIR /build
COPY web/package.json web/vendor.mjs ./
RUN npm install --omit=dev --ignore-scripts && npm run vendor
FROM nginx:1.28-alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY web/index.html web/style.css web/app.js web/tracker-status.js web/car.svg /usr/share/nginx/html/
COPY --from=vendor /build/vendor /usr/share/nginx/html/vendor
EXPOSE 80
