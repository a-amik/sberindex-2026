# Сервис «Пульс МО»: экран прогноза и шоков одним контейнером.
# Интернет нужен только на сборке; данные экрана и контур карты едут внутри образа.
# Реестр базовых образов можно сменить: REGISTRY=mirror.gcr.io/library, если Docker Hub недоступен.
ARG REGISTRY=docker.io/library
FROM ${REGISTRY}/node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM ${REGISTRY}/nginx:1.29-alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=web /web/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD wget -qO- http://127.0.0.1:8080/health || exit 1
