"""In-memory slot template cache — loaded from slot_templates at startup and after admin edits."""
from __future__ import annotations

import logging
from typing import Any

from services.turf_schedule import MAIN_TURF_NAME

log = logging.getLogger(__name__)


async def load_slot_cache(app: Any, pool: Any) -> None:
    """Refresh app.state turf + active slot template maps from the database."""
    async with pool.acquire() as conn:
        turf_row = await conn.fetchrow(
            "SELECT id FROM turfs WHERE name = $1 AND is_active = TRUE LIMIT 1",
            MAIN_TURF_NAME,
        )
        if turf_row:
            app.state.default_turf_id = turf_row["id"]
            slot_rows = await conn.fetch(
                """SELECT id, slot_key, start_time, end_time
                   FROM slot_templates
                   WHERE turf_id = $1 AND is_active = TRUE
                   ORDER BY start_time, slot_key""",
                turf_row["id"],
            )
            app.state.slot_template_ids = {s["slot_key"]: s["id"] for s in slot_rows}
            app.state.slot_templates = {s["slot_key"]: dict(s) for s in slot_rows}
            log.info(
                "Cached turf '%s' with slots: %s",
                MAIN_TURF_NAME,
                list(app.state.slot_template_ids.keys()),
            )
        else:
            app.state.default_turf_id = None
            app.state.slot_template_ids = {}
            app.state.slot_templates = {}
            log.warning("No active turf found when loading slot cache")


def clear_slot_cache(app: Any) -> None:
    app.state.default_turf_id = None
    app.state.slot_template_ids = {}
    app.state.slot_templates = {}
