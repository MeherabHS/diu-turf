# DIU Hostel Turf Booking — Product Requirements & Phase Roadmap

> Status: **Phase 0 (Architecture) + Phase 1 (Authentication) + Phase 2 (Booking Engine) — COMPLETE**

## Phase 2 highlights
- **Booking engine** with 3 fixed daily slots (Asia/Dhaka): A 16:00-17:00 · B 17:00-18:00 · C 18:00-19:00.
- **Strict uniqueness** via two MongoDB partial-unique indexes (one per slot/date, one per user/date) — atomic, race-condition-proof, no app-level locks.
- **Real-time updates** through a single in-process WebSocket pubsub (`/api/ws/bookings`); every create/cancel broadcasts `{type, booking_date, slot_id, booking_id}` to all connected clients.
- **Booking lifecycle**: booked → completed (derived from slot end time) → cancelled (owner or admin).
- **Analytics fields** baked into every row: `day_of_week`, `hour`, `booking_lead_time` (minutes), `department`, `batch` — ML-ready, no separate pipeline yet.
- **Frontend**: 4-tab nav (Home · Book · My Bookings · Profile), date-shift selector, status-coloured slot cards (Available/Booked/My Booking/Completed), confirm modal, success/error Toasts, live WS subscription that triggers silent refetches.

## 1. Vision & Core Problem
Daffodil International University hostel students lack a centralised, fair system to reserve the on-site turf. Multiple groups attempting the same time slot causes daily conflicts. This mobile app solves that with a transparent, real-time booking experience exclusive to `@diu.edu.bd` accounts.

## 2. Tech Stack (as built)
| Layer | Choice | Notes |
|---|---|---|
| Frontend | React Native + Expo SDK 54 + TypeScript (strict) | Expo Router file-based navigation |
| Styling | React Native `StyleSheet` | Per user request; NativeWind avoided |
| Backend | FastAPI + Motor (async MongoDB) | All routes prefixed `/api` |
| Database | MongoDB (Cloud-compatible) | Indexes + TTLs ensured on startup |
| Auth | Emergent-managed Google OAuth → **app-issued JWT** (HS256, 7-day) | All `/api` requests carry `Authorization: Bearer <jwt>` |
| State | **Zustand** store (`useAuthStore`) | Spec-compliant; Phase 0 used Context |
| Forms | **React Hook Form + Zod** | `profileSchema` enforces Name + Student ID rules |
| Date | `date-fns` (already in package.json) | |
| Future analytics | `analytics_events` MongoDB collection (append-only, ML-friendly) | Phase 6+ |

## 3. Folder Structure
```
app/
├── backend/
│   ├── server.py                  # FastAPI app + lifespan
│   ├── routes/
│   │   ├── auth.py                # /api/auth/{session,me,logout}
│   │   ├── users.py               # /api/users/me (profile completion)
│   │   ├── slots.py               # /api/slots (read-only Phase 1)
│   │   └── bookings.py            # /api/bookings/me (stub for Phase 2)
│   └── services/
│       ├── db.py                  # Mongo init + indexes + TTLs
│       ├── models.py              # Pydantic schemas (response models)
│       ├── auth_dep.py            # Bearer auth dependency + RBAC
│       ├── domain.py              # @diu.edu.bd domain check
│       └── seed.py                # Admin + daily slot seeding
└── frontend/
    ├── app/                       # Expo Router file-based routes
    │   ├── _layout.tsx            # Root: SafeAreaProvider + AuthProvider
    │   ├── index.tsx              # Splash + entry router
    │   ├── (auth)/
    │   │   ├── _layout.tsx
    │   │   ├── login.tsx          # Google OAuth screen
    │   │   └── complete-profile.tsx
    │   ├── (tabs)/
    │   │   ├── _layout.tsx        # Bottom tab nav + auth guard
    │   │   ├── index.tsx          # Home dashboard (3 slots)
    │   │   ├── bookings.tsx       # My Bookings (Phase 2 wires data)
    │   │   └── profile.tsx        # Profile + logout
    │   └── (admin)/
    │       ├── _layout.tsx        # Admin role guard
    │       └── dashboard.tsx      # Control room
    └── src/
        ├── components/            # Button, Card, StatusChip, ScreenHeader
        ├── contexts/              # AuthContext.tsx
        ├── services/              # api.ts, authService.ts, slotService.ts
        ├── theme/                 # Design tokens (colors, spacing, type, shadows)
        ├── types/                 # User, Slot, Booking, Role, SlotStatus
        ├── constants/             # ALLOWED_EMAIL_DOMAIN, SESSION_TOKEN_KEY
        ├── hooks/                 # use-icon-fonts (preserved)
        └── utils/storage/         # Cross-platform secure KV (preserved)
```

## 4. Authentication Architecture
**Flow:** Splash → Google OAuth → DIU domain check → (if first login) Profile completion → Home (or Admin dashboard).

1. **Frontend** opens `https://auth.emergentagent.com/?redirect=<scheme>://auth` via `WebBrowser.openAuthSessionAsync` (mobile) or `window.location.href` (web).
2. Google flow returns a one-time `session_id` in the redirect URL hash.
3. Frontend POSTs `{session_token: session_id}` to `/api/auth/session`.
4. Backend calls Emergent's `session-data` endpoint to verify, then **rejects any non-`@diu.edu.bd` email with HTTP 403** before touching the database.
5. Backend upserts the user (`users` collection) and stores the session (`user_sessions` with 7-day TTL).
6. Frontend stores the token in `expo-secure-store` (mobile) / `localStorage` (web) via `@/src/utils/storage.secureSet`.
7. Subsequent requests carry `Authorization: Bearer <token>`. `get_current_user` validates and looks up the user.

**Session persistence:** On every app launch, `AuthContext` calls `/api/auth/me` with the stored token. 401 → token cleared → routed to login.

**Profile completion:** If `profile_completed === false` the router forces `/(auth)/complete-profile` until the user submits a valid `student_id` (regex `^[A-Za-z0-9-]{3,32}$`).

**Route protection:** Each segment layout (`(tabs)/_layout.tsx`, `(admin)/_layout.tsx`) re-checks role + status and `Redirect`s on mismatch. No screen can be reached without satisfying the guard chain.

## 5. Firestore-equivalent — MongoDB Collection Design

### `users`
| Field | Type | Notes |
|---|---|---|
| `user_id` | string (UUID slug) | **PK**, unique index |
| `email` | string | unique index, `@diu.edu.bd` enforced |
| `name` | string | from Google profile |
| `picture` | string \| null | Google avatar URL |
| `role` | `"student" \| "admin"` | RBAC |
| `student_id` | string \| null | captured at profile completion |
| `profile_completed` | bool | gates app entry |
| `created_at`, `updated_at` | UTC datetime | aware |

### `user_sessions`
| Field | Type | Notes |
|---|---|---|
| `session_token` | string | **unique index** |
| `user_id` | string | FK → users |
| `created_at` | UTC datetime | |
| `expires_at` | UTC datetime | **TTL index (`expireAfterSeconds=0`)** |

### `slots`
| Field | Type | Notes |
|---|---|---|
| `slot_id` | string | unique |
| `date` | `YYYY-MM-DD` | compound unique with `slot_key` |
| `slot_key` | `"morning" \| "afternoon" \| "evening"` | |
| `label`, `start_time`, `end_time` | strings | display |
| `status` | `"available" \| "booked" \| "maintenance"` | |
| `booked_by`, `booked_by_name`, `booked_by_student_id` | strings \| null | denormalised for fast reads |

### `bookings`
| Field | Type | Notes |
|---|---|---|
| `booking_id` | string | unique |
| `user_id`, `user_name`, `student_id` | strings | denormalised |
| `slot_id`, `slot_key`, `date` | strings | |
| `status` | `"active" \| "cancelled" \| "completed" \| "expired"` | |
| `created_at` | UTC datetime | |
| `expires_at` | UTC datetime | **TTL → auto-deletes after slot end time** |

**Partial unique indexes** prevent two violations at the DB layer (Phase 2 will create bookings; the indexes already exist):
- One **active** booking per `(user_id, date)` — enforces "one booking per student per day".
- One **active** booking per `(date, slot_key)` — enforces "one student per slot".

### `analytics_events` (ML-ready, Phase 6+)
Append-only log of `event_type` (e.g., `slot_view`, `booking_create`, `booking_cancel`), `user_id`, `slot_key`, `date`, `created_at`, `payload`. Designed to feed pandas / scikit-learn directly.

## 6. Navigation Architecture
```
RootStack (AuthProvider)
├── index            (splash + entry redirect)
├── (auth)/
│   ├── login
│   └── complete-profile
├── (tabs)/          (student bottom tab nav)
│   ├── index        (Home)
│   ├── bookings     (My Bookings)
│   └── profile
└── (admin)/         (role-guarded)
    └── dashboard
```

## 7. User Roles & Permissions
| Capability | Student | Admin |
|---|---|---|
| Sign in (`@diu.edu.bd` only) | ✅ | ✅ |
| View today's slots | ✅ | ✅ |
| Book a slot (Phase 2) | ✅ (1/day) | ❌ (admins manage, don't book) |
| Cancel own booking (Phase 2) | ✅ | ✅ |
| Toggle maintenance (Phase 5) | ❌ | ✅ |
| Force-cancel any booking (Phase 5) | ❌ | ✅ |
| View analytics dashboard (Phase 6) | ❌ | ✅ |

## 8. UI Design System
Sourced from `/app/design_guidelines.json` (Swiss / High-Contrast archetype, DIU green `#50B748`).

- **Colors:** background `#FFFFFF`, primary `#50B748`, status palette for Available / Booked / Maintenance / Selected.
- **Typography:** System font (cross-platform). H1 44pt, H2 30pt, body 16pt, label 11pt uppercase.
- **Spacing scale:** 4 / 8 / 16 / 24 / 32 / 48 / 64.
- **Radii:** sm 8, md 12, lg 16, pill 9999.
- **Components shipped:** `Button` (primary/secondary/ghost), `Card`, `StatusChip`, `ScreenHeader`.
- **Booking states styling** is centralised in `StatusChip`.

## 9. Security Design
- **Backend:** every protected route depends on `get_current_user`, which validates Bearer token → `user_sessions` lookup → TTL check → user lookup. Admin-only routes wrap that with `require_admin`.
- **Frontend:** token in `expo-secure-store` (mobile Keychain) / `localStorage` (web). 401 responses purge the token and route to login.
- **Domain enforcement:** server-side rejection in `/api/auth/session` — cannot be bypassed by tampering with the client.
- **Mongo TTL:** sessions auto-expire after 7 days, bookings auto-expire after slot end.
- **Partial unique indexes:** atomic prevention of duplicate active bookings at the database layer (no race conditions even under load).
- **Future Firestore-equivalent rules** (when porting): use partial indexes + Mongo transactions; for true Firestore, encode rules in `firestore.rules` mirroring `require_admin` and ownership checks.

## 10. Booking System Architecture (designed, not yet built)
Phase 2 will implement:
1. `POST /api/bookings` — server-side transaction:
   - Look up the slot; verify `status == available`.
   - Upsert `bookings` with `(user_id, date)` partial-unique key → duplicate per-day fails.
   - Atomically `$set` slot `status = booked` only `if status == available` (compare-and-set).
   - Emit `analytics_events.booking_create`.
2. **Slot locking** = the partial unique index on `(date, slot_key, status="active")` — Mongo enforces it; no app-level lock needed.
3. **Real-time updates** (Phase 3) via WebSocket channel `/ws/slots/{date}` broadcasting slot mutations; clients reconnect on app foreground.
4. **Auto-expire** = `bookings.expires_at` TTL index already in place.

## 11. Analytics & ML Readiness
Every meaningful user action will emit an immutable doc to `analytics_events` with:
```
{ event_type, user_id, slot_key, date, created_at, payload }
```
Phase 6 aggregates produce slot popularity, hourly demand, no-show rate. Phase 7 trains a demand-prediction model (scikit-learn / Prophet) on a daily snapshot exported as Parquet.

## 12. Phase Roadmap
| Phase | Goal | Deliverables | Dependencies | Complexity |
|---|---|---|---|---|
| **0 — Architecture** ✅ | Foundation, folder layout, types, design system, DB schema | This document, scaffolding, indexes, design tokens | — | Low |
| **1 — Authentication** ✅ | Google OAuth + DIU domain + profile + RBAC | `/api/auth/*`, `/api/users/me`, AuthContext, login + profile screens, admin seed | Phase 0 | Medium |
| **2 — Booking System** | Real booking with locking, one-per-day, cancel | `POST /api/bookings`, `DELETE /api/bookings/{id}`, transactions, slot card actions | Phase 1 | Medium-High |
| **3 — Real-Time Updates** | Live slot status across all clients | WebSocket endpoint, frontend subscription, optimistic UI | Phase 2 | Medium |
| **4 — User Features** | History, search, reminders | My Bookings list, history, in-app notifications surface | Phase 2 | Low-Medium |
| **5 — Admin Dashboard** | Maintenance toggle, force-cancel, user management | Admin routes + UI | Phase 1, 2 | Medium |
| **6 — Analytics** | Slot popularity, peak hours, occupancy | `analytics_events` rollup endpoints, admin charts | Phase 2 | Medium |
| **7 — ML Demand Prediction** | Predict next-week peak slots | Daily Parquet export, sklearn pipeline, `/api/predictions/demand` | Phase 6 | High |
| **8 — Deployment** | Android + iOS builds | Emergent publish flow, EAS-managed builds, store metadata | All | Medium |

## 13. What's Working Right Now
- ✅ Backend boots, indexes + TTLs ensured, admin + 3 slots seeded.
- ✅ `GET /api/health` returns ok.
- ✅ Google OAuth flow end-to-end (mobile + web).
- ✅ Domain enforcement — non-DIU emails get HTTP 403 with clear copy.
- ✅ Profile completion gate.
- ✅ Bottom-tab navigation, admin role auto-routing.
- ✅ Today's slots load on Home; status chips render.
- ✅ Logout clears server session + local token.

## 14. What's Deliberately Deferred
- ❌ Booking mutations (Phase 2).
- ❌ WebSocket real-time push (Phase 3).
- ❌ Maintenance toggle, admin moderation (Phase 5).
- ❌ Analytics rollups, ML (Phase 6-7).
- ❌ Future-day slot scheduling cron (Phase 2 will add).
