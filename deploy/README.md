# Kubernetes deployment for ClearFrame

ClearFrame's API is a **stateless FastAPI container** with **stateful Postgres**.
That is the standard production pattern for both Docker and Kubernetes.

## Docker (single host)

```bash
docker compose up --build
curl -sf http://127.0.0.1:8080/api/ready
```

See root `docker-compose.yml`. Suitable for staging, air-gapped VMs, and small
production footprints. Secrets are injected via environment variables; never
bake them into the image.

## Kubernetes (cluster)

```bash
# 1. Build & push the image your cluster can pull
docker build -t ghcr.io/<org>/clearframe-api:1.0 services/api
docker push ghcr.io/<org>/clearframe-api:1.0

# 2. Edit Secret values in deploy/kubernetes/clearframe.yaml (or use sealed-secrets / External Secrets)

# 3. Apply
kubectl apply -f deploy/kubernetes/clearframe.yaml

# 4. Point CLEARFRAME_CORS at your Pages origin and Ingress host at your DNS
```

### Why this works on Kubernetes

| Concern | How ClearFrame handles it |
|---|---|
| **Process health** | `/api/live` liveness + `/api/ready` readiness (DB ping) |
| **Horizontal scale** | Stateless API replicas + HPA on CPU; shared Postgres |
| **Disruptions** | PodDisruptionBudget keeps ≥1 replica |
| **Secrets** | K8s Secret / External Secrets — production gate refuses defaults |
| **Ingress / TLS** | Standard Ingress; HSTS enabled when TLS terminates |
| **HITL under scale** | Async Aegis queue (`CLEARFRAME_HITL_BLOCKING=false`) — no sticky sessions required |

### What Kubernetes does *not* replace

- Postgres HA (use managed Postgres / Cloud SQL / RDS / operator)
- Object storage for large evidence exports (optional later)
- Identity provider (OIDC already pluggable)

ClearFrame is **ready for Kubernetes today** because the container is production-
gated, probes are correct, and state lives outside the pod. Render's Blueprint
is the managed-PaaS shortcut; Compose is the local/VM path; the manifests in
`deploy/kubernetes/` are the cluster path.
