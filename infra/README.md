# infra — Observability config

Purpose
- Prometheus scrape and Grafana provisioning used to monitor service health,
  calibration metrics, and routing/HITL signals.

Key files
- `prometheus.yml` — scrape configs and job targets
- `grafana/` — provisioning dashboards and datasources

Notes
- All services expose `/metrics`; ensure Prometheus job targets match local
  ports when running `docker compose` during local dev.
