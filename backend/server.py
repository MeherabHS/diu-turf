"""DIU Hostel Turf Booking — FastAPI backend.

Database: PostgreSQL in production · SQLite for local development.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
from dotenv import load_dotenv
from fastapi import FastAPI, Request

from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from database.connection import close_pool, create_pool  # noqa: E402
from database.db_config import DbBackend  # noqa: E402
from database.health import ping_database  # noqa: E402
from database.seed_pg import seed  # noqa: E402
from services.slot_cache import clear_slot_cache, load_slot_cache  # noqa: E402
from routes.activity import router as activity_router  # noqa: E402
from routes.admin import router as admin_router  # noqa: E402
from routes.auth import router as auth_router  # noqa: E402
from routes.bookings import router as bookings_router  # noqa: E402
from routes.users import router as users_router  # noqa: E402
from routes.notifications import router as notifications_router  # noqa: E402
from routes.access_requests import router as access_requests_router  # noqa: E402
from routes.ws import router as ws_router  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

STARTUP_DB_TIMEOUT = float(os.getenv("STARTUP_DB_TIMEOUT", "15"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[STARTUP] creating database pool")
    pool, db_config = await create_pool()
    app.state.db_pool = pool
    app.state.db_config = db_config
    app.state.db_ok = False

    if db_config.backend == DbBackend.SQLITE:
        logger.warning(
            "⚠️  Running in local SQLite development mode. Do not use in production."
        )
        if db_config.fallback_used:
            logger.warning(
                "PostgreSQL was unavailable — using fallback SQLite at %s",
                db_config.sqlite_path,
            )

    try:
        async with asyncio.timeout(STARTUP_DB_TIMEOUT):
            logger.info("[STARTUP] seed begin (timeout=%ss)", STARTUP_DB_TIMEOUT)
            async with pool.acquire() as conn:
                await seed(conn)
            logger.info("[STARTUP] seed done")
            await load_slot_cache(app, pool)
            app.state.db_ok = True
            logger.info("[STARTUP] slot cache loaded")
    except TimeoutError:
        logger.error(
            "[STARTUP] database init timed out after %ss — serving degraded mode",
            STARTUP_DB_TIMEOUT,
        )
        clear_slot_cache(app)
    except Exception:
        logger.exception("[STARTUP] database init failed — serving degraded mode")
        clear_slot_cache(app)

    _dev_flag = os.getenv("DEV_AUTH_ENABLED", "false").lower() in ("1", "true", "yes")
    _env = os.getenv("ENVIRONMENT", "production").lower()
    if _dev_flag and _env != "production":
        logger.warning(
            "⚠️  DEV AUTH ENABLED — POST /api/auth/dev-login is ACTIVE. "
            "Never run this configuration in production."
        )
    elif _dev_flag and _env == "production":
        logger.warning(
            "DEV_AUTH_ENABLED=true was set but ENVIRONMENT=production — "
            "dev-login endpoint is BLOCKED (correct behaviour)."
        )

    backend_label = db_config.backend.value
    if db_config.backend == DbBackend.POSTGRESQL and isinstance(pool, asyncpg.Pool):
        logger.info(
            "[POOL] runtime size=%d idle=%d max=%d",
            pool.get_size(),
            pool.get_idle_size(),
            pool.get_max_size(),
        )
    logger.info("[STARTUP] ready (database=%s db_ok=%s)", backend_label, app.state.db_ok)
    yield
    await close_pool(pool)
    logger.info("Backend shut down")


app = FastAPI(title="DIU Hostel Turf Booking", lifespan=lifespan)


@app.middleware("http")
async def perf_logging_middleware(request: Request, call_next):
    """Lightweight timing — avoids BaseHTTPMiddleware (can hang requests)."""
    env = os.getenv("ENVIRONMENT", "production").lower()
    track = env == "development" and request.url.path.startswith("/api/")
    start = time.perf_counter() if track else None
    response = await call_next(request)
    if track and start is not None:
        ms = (time.perf_counter() - start) * 1000
        logger.info("[PERF] %s %s took %.0fms", request.method, request.url.path, ms)
    return response


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/")
async def root(request: Request):
    logger.info("[ROOT] request received")
    db_config = getattr(request.app.state, "db_config", None)
    backend = db_config.backend.value if db_config else "unknown"
    pool = getattr(request.app.state, "db_pool", None)

    db_ok = False
    if pool is not None:
        logger.info("[ROOT] db check start")
        db_ok = await ping_database(pool)
        logger.info("[ROOT] db check done ok=%s", db_ok)
    else:
        logger.info("[ROOT] db check skipped (no pool)")

    status = "ok" if db_ok else "degraded"
    logger.info("[ROOT] response sent status=%s", status)
    return {
        "service": "DIU Hostel Turf Booking",
        "db": backend,
        "status": status,
    }


@app.get("/api/health")
async def health():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(bookings_router)
app.include_router(activity_router)
app.include_router(admin_router)
app.include_router(notifications_router)
app.include_router(access_requests_router)
app.include_router(ws_router)
