# CedarFix Kubernetes Starter Manifests

This folder deploys the compact CedarFix layout:

- `api-service`: gateway, priority, explanation, review
- `ai-service`: text understanding, embedding, incident matching, routing
- `vision-service`: image understanding
- `frontend`
- `postgres`
- `qdrant`

## Local Kubernetes / Docker Desktop

Build the images locally first:

```powershell
$env:COMPOSE_PARALLEL_LIMIT="1"
docker compose build api-service
docker compose build ai-service
docker compose build vision-service
docker compose build frontend
```

Apply manifests:

```powershell
kubectl apply -k k8s
```

If you want Postgres to run `infra/postgres/init.sql` on a fresh PVC, create this ConfigMap before applying:

```powershell
kubectl create namespace cedarfix
kubectl -n cedarfix create configmap cedarfix-postgres-init --from-file=init.sql=infra/postgres/init.sql
kubectl apply -k k8s
```

Port-forward for local testing:

```powershell
kubectl -n cedarfix port-forward svc/frontend 8080:80
```

Open:

```text
http://localhost:8080
```

## Storage Modes

The app supports two image storage modes:

- `STORAGE_BACKEND=local`: images are saved as `local://filename` under `UPLOADS_DIR`; keep `uploads-pvc`.
- `STORAGE_BACKEND=gcs`: images are saved as stable `gcs://bucket/complaints/filename` refs; set `GCS_BUCKET` and remove the uploads PVC mounts for production.

Do not store signed URLs in Postgres. The gateway generates temporary signed URLs only when serving `/media?ref=...`.

## GKE Notes

Before deploying to GKE:

- Push images to Artifact Registry and replace `image:` values in the manifests.
- Replace `k8s/secrets.example.yaml` values with real secrets or use Secret Manager CSI.
- Prefer Cloud SQL for Postgres instead of in-cluster Postgres.
- Set `STORAGE_BACKEND=gcs` and `GCS_BUCKET=<bucket-name>` for image uploads instead of the shared uploads PVC.
- If using local uploads in GKE, replace `uploads-pvc` with Filestore or another shared storage class. The included PVC is intended for local/single-node Kubernetes.
- Replace `cedarfix.local` in `ingress.yaml` with your real domain.

Useful commands:

```powershell
kubectl -n cedarfix get pods
kubectl -n cedarfix get svc
kubectl -n cedarfix logs deploy/api-service
kubectl -n cedarfix logs deploy/ai-service
kubectl -n cedarfix logs deploy/vision-service
```
