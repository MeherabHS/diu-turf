# CI/CD — DIU Turf

This document describes continuous integration, deployment, and secret management for the DIU Turf project.

## Branch strategy

| Branch | Purpose |
|--------|---------|
| `main` | Production — auto-deploys backend to Render; APK builds use production env |
| Feature branches | Open PRs against `main`; CI runs on push and PR |

Keep `main` deployable at all times. Merge only after CI passes and migrations are reviewed.

---

## GitHub Actions — backend CI

The repository includes `.github/workflows/backend-ci.yml`, which runs on every push and pull request to `main`:

1. **Setup** — Python 3.12, pip cache
2. **Install** — `pip install -r backend/requirements.txt`
3. **Lint (optional)** — `ruff check backend/` when `ruff` is available (non-blocking)
4. **Test** — `pytest backend/tests/ -v` with SQLite test databases

### Running CI locally

```powershell
cd C:\turf\turf2-main\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:ENVIRONMENT = "development"
$env:DATABASE_URL = "sqlite:///./dev_turf.db"
$env:JWT_SECRET = "local-dev-secret-at-least-32-characters-long"
$env:ALLOWED_ORIGINS = "*"
python -m pytest tests/ -v --ignore=tests/test_phase2_bookings.py --ignore=tests/test_phase1_jwt.py
```

---

## Render — backend auto-deploy

**Start command:**

```bash
cd backend && alembic upgrade head && uvicorn server:app --host 0.0.0.0 --port $PORT
```

**Health check path:** `/api/health`

### Render environment variables

| Variable | Production value |
|----------|------------------|
| `DATABASE_URL` | `postgresql://…` |
| `ENVIRONMENT` | `production` |
| `JWT_SECRET` | Strong random string (≥32 chars) |
| `DEV_AUTH_ENABLED` | `false` |
| `ALLOWED_ORIGINS` | `https://diu-turf.onrender.com` (comma-separated if multiple) |
| `SENTRY_DSN` | Optional — Sentry backend DSN |
| Google OAuth client IDs | As configured |

See also [docs/DIGITALOCEAN.md](DIGITALOCEAN.md) and [docs/MONITORING.md](MONITORING.md).

---

## Database migrations

Production deploys run `alembic upgrade head`. Current chain:

| Rev | Summary |
|-----|---------|
| `008` | Booking access roles + `booking_access_requests` |
| `009` | `rate_limit_buckets` for PostgreSQL rate limiting |

---

## EAS — mobile APK

```powershell
cd C:\turf\turf2-main\frontend
$env:EAS_NO_VCS = "1"
npx eas build -p android --profile preview
```

See [docs/APK_SIZE.md](APK_SIZE.md) for optimized local release builds.
