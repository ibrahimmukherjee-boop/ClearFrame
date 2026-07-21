# Deploy ClearFrame (Nexus Protocol)

## Exact webpage

```
http://YOUR-EC2-PUBLIC-IP:8080/
```

## Login details

**None.** Demo mode ships with authentication disabled.

| Field | Value |
|-------|--------|
| Username | — |
| Password | — |
| Token | — |

## EC2 install

```bash
git clone -b cursor/nexus-sandbox-demo-be86 \
  https://github.com/ibrahimmukherjee-boop/ClearFrame.git
cd ClearFrame
bash clearframe/deploy/install-ec2.sh
```

Open security group port **8080**.

## Docker

```bash
docker compose up --build -d
```

## Health check

```bash
curl -s http://127.0.0.1:8080/health | python3 -m json.tool
```

Expect `"auth_required": false` and all services `"ok": true`.
