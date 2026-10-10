FROM node:22-alpine AS vendor
WORKDIR /build
COPY web/package.json web/vendor.mjs ./
RUN npm install --omit=dev --ignore-scripts && npm run vendor
FROM nginx:1.28-alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY web/index.html web/style.css web/app.js web/tracker-status.js web/convenience.js web/manifest.webmanifest web/safdecor-logo.svg web/safdecor-mark.svg web/car.svg web/car-safdecor.webp web/safdecor-wordmark.png /usr/share/nginx/html/
COPY --from=vendor /build/vendor /usr/share/nginx/html/vendor
COPY web/icons /usr/share/nginx/html/icons
COPY web/fonts /usr/share/nginx/html/fonts
EXPOSE 80
