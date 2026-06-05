# CedarFix GCP Deployment Profile

This profile is for GKE with no app data stored in pods.

It excludes:

- in-cluster Postgres
- in-cluster Qdrant
- uploads PVC

It expects:

- Cloud SQL PostgreSQL
- GCS for complaint images
- Qdrant Cloud or another managed Qdrant endpoint
- Artifact Registry images
- Workload Identity for Cloud SQL and GCS

## 1. Replace Placeholders

Replace these strings in `k8s-gcp/*.yaml`:

- `PROJECT_ID`
- `REGION`
- `YOUR_GCS_BUCKET`
- `YOUR_QDRANT_CLUSTER_URL`
- `YOUR_TEXT_QWEN_RUNPOD.proxy.runpod.net`
- `YOUR_VLM_RUNPOD.proxy.runpod.net`
- `cedarfix.example.com`

## 2. Required GCP Resources

Enable APIs:

```powershell
gcloud services enable container.googleapis.com artifactregistry.googleapis.com sqladmin.googleapis.com storage.googleapis.com secretmanager.googleapis.com iam.googleapis.com
```

Create Artifact Registry:

```powershell
gcloud artifacts repositories create cedarfix --repository-format=docker --location=REGION
gcloud auth configure-docker REGION-docker.pkg.dev
```

Create GCS bucket:

```powershell
gcloud storage buckets create gs://YOUR_GCS_BUCKET --location=REGION --uniform-bucket-level-access
```

Create Cloud SQL:

```powershell
gcloud sql instances create cedarfix-postgres --database-version=POSTGRES_15 --region=REGION --tier=db-custom-2-7680 --storage-size=20GB --storage-type=SSD
gcloud sql databases create cedarfix --instance=cedarfix-postgres
gcloud sql users create cedarfix --instance=cedarfix-postgres --password=STRONG_DB_PASSWORD
```

Create GKE:

```powershell
gcloud container clusters create cedarfix-gke --region REGION --num-nodes 2 --machine-type e2-standard-4 --enable-ip-alias --workload-pool=PROJECT_ID.svc.id.goog
gcloud container clusters get-credentials cedarfix-gke --region REGION
```

Create static IP:

```powershell
gcloud compute addresses create cedarfix-ip --global
```

## 3. Workload Identity

Create a Google service account:

```powershell
gcloud iam service-accounts create cedarfix-gke --display-name="CedarFix GKE"
```

Grant Cloud SQL and GCS access:

```powershell
gcloud projects add-iam-policy-binding PROJECT_ID --member="serviceAccount:cedarfix-gke@PROJECT_ID.iam.gserviceaccount.com" --role="roles/cloudsql.client"
gcloud storage buckets add-iam-policy-binding gs://YOUR_GCS_BUCKET --member="serviceAccount:cedarfix-gke@PROJECT_ID.iam.gserviceaccount.com" --role="roles/storage.objectAdmin"
```

Allow the Kubernetes service account to impersonate it:

```powershell
gcloud iam service-accounts add-iam-policy-binding cedarfix-gke@PROJECT_ID.iam.gserviceaccount.com --role roles/iam.workloadIdentityUser --member "serviceAccount:PROJECT_ID.svc.id.goog[cedarfix/cedarfix-app]"
```

## 4. Build And Push Images

```powershell
docker build -t REGION-docker.pkg.dev/PROJECT_ID/cedarfix/cedarfix-api:latest -f docker/api.Dockerfile .
docker build -t REGION-docker.pkg.dev/PROJECT_ID/cedarfix/cedarfix-ai:latest -f docker/ai.Dockerfile .
docker build -t REGION-docker.pkg.dev/PROJECT_ID/cedarfix/cedarfix-vision-ai:latest -f docker/vision.Dockerfile .
docker build -t REGION-docker.pkg.dev/PROJECT_ID/cedarfix/cedarfix-frontend:latest -f services/frontend/Dockerfile services/frontend

docker push REGION-docker.pkg.dev/PROJECT_ID/cedarfix/cedarfix-api:latest
docker push REGION-docker.pkg.dev/PROJECT_ID/cedarfix/cedarfix-ai:latest
docker push REGION-docker.pkg.dev/PROJECT_ID/cedarfix/cedarfix-vision-ai:latest
docker push REGION-docker.pkg.dev/PROJECT_ID/cedarfix/cedarfix-frontend:latest
```

## 5. Create Secrets

Create the secret manually, or copy `secrets.example.yaml`, fill values, and apply it.

Manual command:

```powershell
kubectl create namespace cedarfix
kubectl -n cedarfix create secret generic cedarfix-secrets `
  --from-literal=DATABASE_URL="postgresql://cedarfix:STRONG_DB_PASSWORD@127.0.0.1:5432/cedarfix" `
  --from-literal=JWT_SECRET_KEY="LONG_RANDOM_SECRET" `
  --from-literal=OPENAI_API_KEY="YOUR_OPENAI_KEY" `
  --from-literal=QWEN_API_KEY="none" `
  --from-literal=VLM_API_KEY="none" `
  --from-literal=QDRANT_API_KEY="YOUR_QDRANT_API_KEY"
```

## 6. Initialize Cloud SQL Schema

Run this once after Cloud SQL is reachable:

```powershell
psql "postgresql://cedarfix:STRONG_DB_PASSWORD@CLOUD_SQL_HOST:5432/cedarfix" -f infra/postgres/init.sql
```

If using only the Cloud SQL proxy, run it from a temporary pod or your local Cloud SQL Auth Proxy.

## 7. Deploy

```powershell
kubectl apply -k k8s-gcp
kubectl -n cedarfix get pods
kubectl -n cedarfix get ingress
```

## 8. Post-Deploy Checks

```powershell
kubectl -n cedarfix logs deploy/api-service
kubectl -n cedarfix logs deploy/ai-service
kubectl -n cedarfix logs deploy/vision-service
```

Test:

- signup/login
- image complaint upload
- admin image preview
- duplicate detection
- RAG routing
