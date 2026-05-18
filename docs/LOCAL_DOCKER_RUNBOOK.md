# CedarFix Local Docker Runbook

Purpose: start the Phase 1 stack without leaking unrelated local secrets into containers.

---

## One-Time Setup

Create a CedarFix-only env file:

```powershell
Copy-Item .env.cedarfix.example .env.cedarfix
```

Do not put GitHub tokens, cloud credentials, or personal API keys in `.env.cedarfix`.

---

## Start The Stack

```powershell
docker compose --env-file .env.cedarfix up --build
```

Services:

| Service | URL |
|---|---|
| EEP | `http://localhost:8000/health` |
| IEP-1 | `http://localhost:8001/health` |
| Postgres | `127.0.0.1:5432` only |
| Redis | `127.0.0.1:6379` only |

Postgres and Redis are intentionally bound to `127.0.0.1` so they are not exposed on the LAN.

---

## Smoke Test

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/complaints `
  -ContentType "application/json" `
  -Body '{"text":"fi jora kbire 3al tari2 w l wad3 m5atra ktir","gps_lat":33.8897,"gps_lon":35.48,"language_hint":"arabizi"}'
```

Then poll the returned `status_url`.

---

## Local `.env` Warning

Docker Compose auto-loads `.env` by default. If your local `.env` contains unrelated secrets or invalid syntax, use the explicit CedarFix env file command above.

If a token was ever pasted into `.env`, rotate that token before pushing or presenting.
