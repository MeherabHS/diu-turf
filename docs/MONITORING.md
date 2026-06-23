# Production Monitoring — Sentry

DIU Turf uses [Sentry](https://sentry.io) for crash and error monitoring on both the **Expo React Native app** and the **FastAPI backend**. Sentry is optional in local development: if the DSN environment variables are not set, the SDKs stay disabled and the app behaves exactly as before.

## Why Sentry?

| Benefit | Details |
|---------|---------|
| **Crash reports** | Native Android crashes + unhandled JS exceptions in the mobile app |
| **Backend errors** | Unhandled FastAPI exceptions and HTTP 500 responses |
| **Release tracking** | Group errors by app/backend version |
| **Alerts** | Email or Slack when new issues appear or error rates spike |
| **Free tier** | 5,000 events/month on Sentry's free Developer plan |

Sentry complements (does not replace) uptime checks. See [Uptime monitoring](#uptime-monitoring-complement) below.

---

## Step 1 — Create Sentry projects

1. Sign up at [sentry.io](https://sentry.io/signup/) (free tier is sufficient to start).
2. Create **two projects** in the same organization:
   - **React Native** — for the DIU Turf mobile app
   - **Python / FastAPI** — for the Render backend
3. For each project, open **Settings → Client Keys (DSN)** and copy the DSN. It looks like:

   ```
   https://<publicKey>@o<orgId>.ingest.sentry.io/<projectId>
   ```

   Never commit real DSNs to git. Use environment variables only.

---

## Step 2 — Configure the backend (Render)

In the [Render dashboard](https://dashboard.render.com) for the DIU Turf web service, add:

| Variable | Example | Required |
|----------|---------|----------|
| `SENTRY_DSN` | `https://…@o….ingest.sentry.io/…` | Yes (for monitoring) |
| `ENVIRONMENT` | `production` | Already set |
| `SENTRY_RELEASE` | `diu-turf-backend@1.0.0` | Optional — groups errors by deploy |
| `SENTRY_TRACES_SAMPLE_RATE` | `0` | Optional — `0` disables performance tracing |

Redeploy the backend after saving. No APK rebuild is needed for backend-only changes.

### Verify backend

After deploy, trigger a test error (temporary — remove after verifying):

```python
# Add to a route or run in Render shell, then remove:
raise RuntimeError("Sentry backend test — delete me")
```

Or call a one-off debug route if you add one locally. Within ~30 seconds the event should appear in the **Python/FastAPI** Sentry project under **Issues**.

---

## Step 3 — Configure the frontend (EAS)

The mobile SDK requires a **native rebuild** after adding Sentry (first time only). OTA updates alone cannot add the native Sentry module.

### Local `.env` (optional — for testing)

In `frontend/.env`:

```env
EXPO_PUBLIC_SENTRY_DSN=https://…@o….ingest.sentry.io/…
EXPO_PUBLIC_ENVIRONMENT=production
# EXPO_PUBLIC_SENTRY_DEBUG=true   # only when testing from __DEV__ builds
```

### EAS build secrets (recommended for preview/production)

Set the DSN via EAS secrets so it is not baked into `eas.json`:

```powershell
cd frontend
npx eas secret:create --scope project --name EXPO_PUBLIC_SENTRY_DSN --value "https://…@o….ingest.sentry.io/…"
```

`eas.json` includes an empty `EXPO_PUBLIC_SENTRY_DSN` placeholder for preview/production profiles — override it with EAS secrets or set the value in the Render/EAS dashboard before building.

### Source maps (optional, recommended)

For readable stack traces in production builds, configure the Sentry Expo plugin in `app.json` with your org/project and add an auth token:

1. Sentry → **Settings → Auth Tokens** → create token with `project:releases` scope.
2. Add `SENTRY_AUTH_TOKEN` as an EAS secret (never commit it).
3. Optionally extend the `@sentry/react-native` plugin in `app.json`:

   ```json
   [
     "@sentry/react-native/expo",
     {
       "organization": "your-org-slug",
       "project": "your-react-native-project-slug"
     }
   ]
   ```

### Rebuild the APK

```powershell
cd frontend
npx eas build -p android --profile preview
```

### Verify frontend

In a **release/preview build** (not Expo Go), temporarily add a test button:

```tsx
import * as Sentry from "@sentry/react-native";

// onPress:
Sentry.captureException(new Error("Sentry mobile test — delete me"));
```

Or throw an unhandled error. Check the **React Native** Sentry project → **Issues**.

---

## Dashboard overview

| View | Use |
|------|-----|
| **Issues** | Grouped errors with stack traces, frequency, last seen |
| **Releases** | Errors per `SENTRY_RELEASE` / app version |
| **Alerts** | Project Settings → Alerts → e.g. email when a new issue is created |
| **Performance** | Optional — enable via `SENTRY_TRACES_SAMPLE_RATE` (backend) |

Suggested alert: **“A new issue is created”** → email to the team.

---

## Uptime monitoring (complement)

Sentry reports **application errors**; it does not tell you when Render is down entirely.

| Tool | Role |
|------|------|
| **Render health check** | Point at `GET https://diu-turf.onrender.com/api/health` |
| **[UptimeRobot](https://uptimerobot.com)** (free) | External ping every 5 minutes; email on downtime |

Use both: UptimeRobot for “is the server reachable?”, Sentry for “is the app throwing exceptions?”.

---

## Privacy and data scrubbing

Both SDKs are configured with **`send_default_pii=False`**.

Additional scrubbing:

| Layer | What is scrubbed |
|-------|------------------|
| **Backend** (`services/sentry_config.py`) | Email patterns in request data; `Authorization` / `Cookie` headers; user context limited to `id` |
| **Frontend** (`src/config/sentry.ts`) | `user.email` and email-like usernames removed in `beforeSend` |

What **is** typically sent: error message, stack trace, device/OS info, app version, request path (backend), breadcrumbs.

What is **not** sent by default: passwords, JWT tokens, full request bodies with PII.

Review each issue in Sentry before sharing externally. Adjust `before_send` in `sentry_config.py` / `sentry.ts` if your routes add sensitive fields.

---

## Local development

| Scenario | Behaviour |
|----------|-----------|
| No DSN set | Sentry disabled; app and backend start normally |
| Backend tests | `pytest` passes without Sentry; see `tests/test_sentry_config.py` |
| Frontend `__DEV__` | Events suppressed unless `EXPO_PUBLIC_SENTRY_DEBUG=true` |

---

## Environment variable reference

### Backend (`backend/.env`)

| Variable | Description |
|----------|-------------|
| `SENTRY_DSN` | Sentry project DSN — unset = disabled |
| `SENTRY_RELEASE` | Release name shown in Sentry (e.g. `diu-turf-backend@1.0.0`) |
| `SENTRY_TRACES_SAMPLE_RATE` | `0`–`1.0`; default `0` (errors only) |

### Frontend (`frontend/.env` / EAS)

| Variable | Description |
|----------|-------------|
| `EXPO_PUBLIC_SENTRY_DSN` | Sentry React Native project DSN |
| `EXPO_PUBLIC_ENVIRONMENT` | `development` / `preview` / `production` |
| `EXPO_PUBLIC_SENTRY_DEBUG` | `true` to send events from dev builds (testing only) |

---

## Related docs

- [README — Monitoring](../README.md#monitoring)
- [CI/CD and deployment](CI_CD.md)
- [Expo + Sentry guide](https://docs.expo.dev/guides/using-sentry/)
- [Sentry FastAPI docs](https://docs.sentry.io/platforms/python/integrations/fastapi/)
