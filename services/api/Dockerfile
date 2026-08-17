FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
COPY vendor /app/vendor
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

ENV PYTHONUNBUFFERED=1
ENV CLEARFRAME_API_HOST=0.0.0.0
ENV CLEARFRAME_API_PORT=8080
ENV CLEARFRAME_DATA_DIR=/data
ENV CLEARFRAME_AUTH=true
ENV USE_CLEARFRAME_RUNTIME=true
ENV CLEARFRAME_RELOAD=false
ENV USE_CLEARFRAME_OPS=true
ENV USE_OLLAMA=false
ENV CLEARFRAME_HSTS=false

VOLUME /data
EXPOSE 8080

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
