# DigitalOcean Database Guide — DIU Turf

This guide explains how to run **DIU Turf** with a **Render backend** and a **DigitalOcean PostgreSQL** database. The mobile APK and frontend stay pointed at `https://diu-turf.onrender.com` — no app rebuild required.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Budget & hosting options](#budget--hosting-options)
3. [Prerequisites](#prerequisites)
4. [Step 1 — Create a DigitalOcean Managed PostgreSQL cluster](#step-1--create-a-digitalocean-managed-postgresql-cluster)
5. [Step 2 — Firewall & trusted sources (Render)](#step-2--firewall--trusted-sources-render)
6. [Step 3 — Enable required extensions](#step-3--enable-required-extensions)
7. [Step 4 — Database setup (migrate or restore)](#step-4--database-setup-migrate-or-restore)
8. [Step 5 — Update Render environment variables](#step-5--update-render-environment-variables)
9. [Step 6 — Verify deployment](#step-6--verify-deployment)
10. [Connection string format (asyncpg)](#connection-string-format-asyncpg)
11. [DigitalOcean control panel checklist](#digitalocean-control-panel-checklist)
12. [Rollback plan](#rollback-plan)
13. [What NOT to change](#what-not-to-change)
14. [Local development (unchanged)](#local-development-unchanged)
15. [Troubleshooting](#troubleshooting)

---

## Architecture

```
┌─────────────────────┐         HTTPS/WSS          ┌──────────────────────┐
│  DIU Turf APK       │ ─────────────────────────► │  Render Web Service  │
│  (Expo / Android)   │   diu-turf.onrender.com    │  FastAPI + asyncpg   │
└─────────────────────┘                            └──────────┬───────────┘
                                                               │
                                                               │ PostgreSQL
                                                               │ (SSL required)
                                                               ▼
                                                    ┌──────────────────────┐
                                                    │  DigitalOcean        │
                                                    │  Managed PostgreSQL  │
                                                    └──────────────────────┘
```

| Component | Host | Notes |
|-----------|------|-------|
| Mobile app | User devices | API base URL unchanged (`https://diu-turf.onrender.com`) |
| Backend API | **Render** | Existing start command, health checks, env vars |
| Database | **DigitalOcean** | Managed PostgreSQL with SSL |
| Local dev | Your machine | SQLite fallback still works — no DO account needed |

**Why split Render + DO?** Render’s free/cheap tiers include limited PostgreSQL storage and expire after 90 days on free DB plans. Moving the database to DigitalOcean gives you persistent storage, automated backups, and clearer scaling — while keeping the API on Render without rebuilding the APK.

---

## Budget & hosting options

Target budget: **~$12/month**.

| Option | Approx. cost | Pros | Cons |
|--------|--------------|------|------|
| **DO Managed PostgreSQL (smallest)** | **~$15/mo** | Automated backups, patches, monitoring, SSL, point-in-time recovery | Slightly over $12 budget; least ops work |
| **DO Droplet + self-hosted Postgres** | **$6–12/mo** (Droplet) | Fits budget; full control | You manage backups, upgrades, security, disk; no managed failover |
| **Keep Render Postgres** | $0–7/mo (plan dependent) | Simplest; no cross-cloud networking | Free tier expires; storage/connection limits |

**Honest recommendation for a portfolio/student project:**

- If you can stretch to **$15/mo**, use **Managed PostgreSQL** — the time saved on backups and maintenance is worth it.
- If you must stay under **$12/mo**, a **$6 Basic Droplet** with self-hosted PostgreSQL works, but budget time for weekly backups (`pg_dump` cron) and security updates.
- This codebase is ready for **Managed PostgreSQL** out of the box; self-hosted Droplet Postgres uses the same connection string format.

---

## Prerequisites

- DigitalOcean account
- Existing Render service: `diu-turf.onrender.com`
- `psql`, `pg_dump`, and `pg_restore` installed locally (PostgreSQL client tools)
- Git repo with latest backend changes (SSL-aware `connection.py`)

---

## Step 1 — Create a DigitalOcean Managed PostgreSQL cluster

1. Log in to [DigitalOcean](https://cloud.digitalocean.com/).
2. **Create → Databases → PostgreSQL**.
3. Choose:
   - **Region**: closest to your users (e.g. `Singapore` or `Bangalore` for Bangladesh) — also consider Render’s region for latency.
   - **Plan**: Basic → **1 GB RAM / 1 vCPU / 10 GB disk** (~$15/mo).
   - **PostgreSQL version**: **15** or **16** (project targets PostgreSQL 14+).
   - **Database name**: e.g. `turf_db` (or use default `defaultdb`).
4. Click **Create Database Cluster** and wait for status **Online** (~3–5 minutes).
5. Open the cluster → **Connection Details**:
   - Note **Host**, **Port**, **User**, **Password**, **Database**, **SSL mode**.
   - Download the **CA certificate** (optional; `ssl=True` with asyncpg works for most cases).

**Example connection string** (DigitalOcean format):

```
postgresql://doadmin:YOUR_PASSWORD@db-postgresql-nyc3-12345.db.ondigitalocean.com:25060/defaultdb?sslmode=require
```

> Keep `?sslmode=require` in the URL. The backend auto-detects this and passes `ssl=True` to asyncpg (which does not read libpq `sslmode` on its own).

---

## Step 2 — Firewall & trusted sources (Render)

DigitalOcean Managed PostgreSQL only accepts connections from **trusted sources**.

**The Render challenge:** Render web services use **dynamic outbound IP addresses** unless you pay for a static outbound IP add-on. You cannot whitelist a single permanent Render IP on the free tier.

**Practical options:**

| Approach | Security | Effort |
|----------|----------|--------|
| **Allow all IPv4** (`0.0.0.0/0`) in DO trusted sources | Lower — mitigated by strong password + mandatory SSL | Easiest; common for small projects |
| **Render static outbound IP** (paid add-on) | Higher — whitelist that IP only | Best for production |
| **Run backend on DO Droplet** (same VPC as DB) | Highest — private network | More migration work; not needed now |

**To add trusted sources in DO:**

1. Database cluster → **Settings → Trusted Sources**.
2. Add:
   - Your home/office IP (for `psql` / migrations from laptop), **and**
   - Either `0.0.0.0/0` (all IPv4) for Render, **or** your Render static outbound IP.
3. Save. Changes apply within ~1 minute.

> SSL is required for DO Managed PostgreSQL regardless of firewall rules. Never disable SSL in production.

---

## Step 3 — Enable required extensions

DIU Turf migrations expect two PostgreSQL extensions (created in migration `001`):

| Extension | Purpose |
|-----------|---------|
| `pgcrypto` | `gen_random_uuid()` for UUID primary keys |
| `citext` | Case-insensitive unique email (`CITEXT` column type) |

**Option A — Let Alembic create them (recommended)**

Migration `001_initial_schema.py` runs:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
```

If your DO database user has `CREATE` privilege on the database (default `doadmin` does), extensions are created automatically on `alembic upgrade head`.

**Option B — Enable manually in DO SQL console**

1. Cluster → **Console** (or connect with `psql`).
2. Run:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
```

3. Verify:

```sql
SELECT extname FROM pg_extension WHERE extname IN ('pgcrypto', 'citext');
```

---

## Step 4 — Database setup (migrate or restore)

Choose **one** path.

### Path A — Migrate existing data from Render Postgres

Use this if you have live users/bookings on Render’s database.

**1. Dump from Render** (from your laptop; use Render’s **External** database URL):

```bash
pg_dump "postgresql://USER:PASS@RENDER_HOST:5432/DBNAME" \
  --format=custom \
  --no-owner \
  --no-acl \
  -f turf_render_backup.dump
```

**2. Restore to DigitalOcean:**

```bash
pg_restore \
  --dbname="postgresql://doadmin:YOUR_PASSWORD@db-postgresql-nyc3-12345.db.ondigitalocean.com:25060/defaultdb?sslmode=require" \
  --no-owner \
  --no-acl \
  --clean \
  --if-exists \
  turf_render_backup.dump
```

**3. Confirm Alembic revision** (optional — dump may already include `alembic_version`):

```bash
cd backend
export DATABASE_URL="postgresql://doadmin:YOUR_PASSWORD@db-postgresql-nyc3-12345.db.ondigitalocean.com:25060/defaultdb?sslmode=require"
python -m alembic current
```

If behind, run `python -m alembic upgrade head`.

### Path B — Fresh start (empty database)

Use this for a new deployment or when test data can be discarded.

```bash
cd backend
export DATABASE_URL="postgresql://doadmin:YOUR_PASSWORD@db-postgresql-nyc3-12345.db.ondigitalocean.com:25060/defaultdb?sslmode=require"
python -m alembic upgrade head
```

Startup seed (`seed_pg.py`) runs automatically on first Render deploy — admin user, turf, and slot templates are created idempotently.

---

## Step 5 — Update Render environment variables

In [Render Dashboard](https://dashboard.render.com/) → your web service → **Environment**:

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | Full DO connection string with `?sslmode=require` |
| `ENVIRONMENT` | `production` (unchanged) |
| `DEV_AUTH_ENABLED` | `false` (unchanged) |
| `JWT_SECRET` | unchanged |
| Google OAuth vars | unchanged |

**Optional override:**

| Variable | When to use |
|----------|-------------|
| `DATABASE_SSL=true` | Force SSL if URL has no `sslmode` param |
| `DATABASE_SSL=false` | Local/dev only — never in production with DO |

**Do not change** the Render start command:

```bash
cd backend && alembic upgrade head && uvicorn server:app --host 0.0.0.0 --port $PORT
```

Save env vars → Render triggers a **manual deploy** or auto-redeploy.

---

## Step 6 — Verify deployment

After Render finishes deploying:

**1. Liveness (no DB check):**

```bash
curl https://diu-turf.onrender.com/api/health
# Expected: {"status":"ok"}
```

**2. Database connectivity:**

```bash
curl https://diu-turf.onrender.com/api/
# Expected: {"service":"DIU Hostel Turf Booking","db":"postgresql","status":"ok"}
```

If `"status":"degraded"`, check Render logs for:

- `PostgreSQL unavailable` — firewall, wrong password, or missing SSL
- `Could not connect to PostgreSQL` — trusted sources or `DATABASE_URL` typo
- Migration errors — extensions or Alembic revision mismatch

**3. Functional smoke test:**

- `GET /docs` loads OpenAPI UI
- `POST /api/auth/login` with a known account (or register a test user)
- Admin dashboard loads bookings

**4. Render logs — success indicators:**

```
[POOL] postgresql min_size=1 max_size=10 ...
[STARTUP] seed done
[STARTUP] ready (database=postgresql db_ok=True)
```

---

## Connection string format (asyncpg)

DIU Turf uses **asyncpg** at runtime and **SQLAlchemy + asyncpg** for Alembic. Neither reads libpq `sslmode` from the URL automatically.

| Layer | URL format | SSL handling |
|-------|------------|--------------|
| **Render env `DATABASE_URL`** | `postgresql://user:pass@host:25060/db?sslmode=require` | Backend strips `sslmode` and sets `ssl=True` |
| **Alembic migrations** | Same `DATABASE_URL` | `connect_args={"ssl": True}` in `alembic/env.py` |
| **Local SQLite dev** | `sqlite:///./dev_turf.db` | SSL not applicable |

**DigitalOcean example (copy to Render):**

```
postgresql://doadmin:YOUR_PASSWORD@db-postgresql-nyc3-12345.db.ondigitalocean.com:25060/defaultdb?sslmode=require
```

**Render Postgres example (still works — no code change):**

```
postgresql://user:pass@dpg-xxxxx-a.oregon-postgres.render.com/turf_db
```

Render internal URLs often omit `sslmode`; SSL auto-detection leaves asyncpg defaults (works for Render).

---

## DigitalOcean control panel checklist

Use this after initial setup and before go-live:

- [ ] Cluster status **Online**
- [ ] PostgreSQL version ≥ 14
- [ ] Trusted sources include Render access (all IPv4 or static IP)
- [ ] Your dev machine IP added for `psql` / emergency access
- [ ] Extensions `pgcrypto` and `citext` present
- [ ] Connection string copied with `sslmode=require`
- [ ] Automated backups enabled (default on Managed PG)
- [ ] Database password stored in password manager (not committed to git)
- [ ] Render `DATABASE_URL` updated and deploy succeeded
- [ ] `GET /api/` returns `"db":"postgresql","status":"ok"`

---

## Rollback plan

If the DO migration fails or causes production issues:

1. **Render → Environment** → restore the previous `DATABASE_URL` (Render Postgres).
2. **Manual Deploy** on Render.
3. Verify `GET /api/` returns `"status":"ok"`.
4. Investigate DO logs / Render logs offline — the APK and frontend need no changes.

**Data note:** If you ran Path B (fresh start) on DO but need old data, restore from your `pg_dump` backup or keep Render Postgres running until DO is verified.

**DO cluster:** Leave running during rollback (no cost if you destroy later) or destroy from **Settings → Destroy** once confident.

---

## What NOT to change

| Item | Reason |
|------|--------|
| **APK / mobile app** | API URL stays `https://diu-turf.onrender.com` |
| **`frontend/.env`** | No backend URL change needed |
| **Render service URL** | Students already use this endpoint |
| **Local SQLite workflow** | `DATABASE_URL=sqlite:///./dev_turf.db` still works for dev |
| **Google OAuth client IDs** | Unrelated to database host |
| **WebSocket URL** | Still `wss://diu-turf.onrender.com/api/ws/bookings` |

---

## Local development (unchanged)

Local dev does **not** require DigitalOcean:

```powershell
cd backend
Copy-Item .env.example .env
# DATABASE_URL=sqlite:///./dev_turf.db  (default)
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

To test against DO from your laptop:

```powershell
$env:DATABASE_URL="postgresql://doadmin:PASS@db-postgresql-....ondigitalocean.com:25060/defaultdb?sslmode=require"
python -m alembic upgrade head
uvicorn server:app --host 0.0.0.0 --port 8001
```

Ensure your IP is in DO **Trusted Sources**.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `PostgreSQL unavailable (SSL)` | Missing `ssl=True` / no `sslmode=require` | Add `?sslmode=require` or `DATABASE_SSL=true` |
| Connection timeout | Firewall / trusted sources | Add Render IP or `0.0.0.0/0`; add your IP for local |
| `extension "citext" does not exist` | Extensions not enabled | Run Step 3 SQL or `alembic upgrade head` as superuser |
| `password authentication failed` | Wrong credentials | Reset password in DO → Users; update Render env |
| `"status":"degraded"` on `/api/` | Pool connected but seed/cache failed | Check Render logs; verify migrations applied |
| Alembic SSL error locally | Old client / missing sslmode | Use full DO URL with `?sslmode=require` |

---

## Related files in this repo

| File | Role |
|------|------|
| `backend/database/db_config.py` | `prepare_postgres_connection()` — SSL auto-detect |
| `backend/database/connection.py` | asyncpg pool with SSL |
| `backend/alembic/env.py` | Alembic SSL `connect_args` |
| `backend/.env.example` | DO connection string template |
| `backend/alembic/versions/001_initial_schema.py` | Creates `pgcrypto`, `citext` |

---

*Last updated: June 2026 · DIU Turf · Render backend + DigitalOcean PostgreSQL*
