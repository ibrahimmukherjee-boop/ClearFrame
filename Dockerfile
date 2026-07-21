# ClearFrame — production container
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CLEARFRAME_HOST=0.0.0.0 \
    CLEARFRAME_PORT=8080 \
    CLEARFRAME_DEMO=1 \
    NEXUS_HOME=/data/nexus

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Copy monorepo pieces needed for full stack
COPY clearframe /app/clearframe
COPY nexus-sandbox/components /app/nexus-sandbox/components

RUN pip install --no-cache-dir \
      -e /app/clearframe \
      -e /app/nexus-sandbox/components/trust-registry \
      -e /app/nexus-sandbox/components/aegis \
      -e /app/nexus-sandbox/components/sonar

EXPOSE 8080
VOLUME ["/data/nexus"]

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/health || exit 1

CMD ["clearframe", "serve", "--host", "0.0.0.0", "--port", "8080"]
