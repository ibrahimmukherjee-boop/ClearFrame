FROM node:22-alpine AS frontend-build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
COPY backend/vendor backend/vendor
WORKDIR /app/backend
RUN pip install --no-cache-dir -r requirements.txt
WORKDIR /app

COPY backend backend
COPY --from=frontend-build /app/dist /app/backend/static

ENV CLEARFRAME_API_HOST=0.0.0.0
ENV CLEARFRAME_API_PORT=8080
ENV CLEARFRAME_DATA_DIR=/data
ENV CLEARFRAME_AUTH=true
ENV USE_CLEARFRAME_RUNTIME=true
ENV CLEARFRAME_RELOAD=false
ENV USE_CLEARFRAME_OPS=true

VOLUME /data
EXPOSE 8080 7477

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
