import aiosqlite
from database.db import DB_PATH


async def log_action(user_id: int, action: str, data: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO analytics (user_id, action, data) VALUES (?,?,?)",
            (user_id, action, data)
        )
        await db.commit()


async def get_action_count(action: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT COUNT(*) as c FROM analytics WHERE action=?", (action,)
        ) as cur:
            return (await cur.fetchone())["c"]


async def get_recent_actions(limit: int = 50):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM analytics ORDER BY id DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ─── REQUIRED CHANNELS ────────────────────────────────────────

async def _ensure_channel_columns(db):
    """Safe migrations — add new columns without breaking existing data."""
    for col, dflt in [
        ("channel_type", "TEXT DEFAULT 'public'"),
        ("invite_link",  "TEXT"),
        ("username",     "TEXT"),
    ]:
        try:
            await db.execute(f"ALTER TABLE required_channels ADD COLUMN {col} {dflt}")
            await db.commit()
        except Exception:
            pass  # column already exists


async def get_required_channels():
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_channel_columns(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, channel_id, title, username, "
            "COALESCE(channel_type, 'public') as channel_type, "
            "invite_link, added_at FROM required_channels"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def add_required_channel(
    channel_id: str,
    title: str = None,
    channel_type: str = "public",
    invite_link: str = None,
    username: str = None,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_channel_columns(db)
        async with db.execute(
            "SELECT id FROM required_channels WHERE channel_id=?", (channel_id,)
        ) as cur:
            existing = await cur.fetchone()
        if existing:
            await db.execute(
                "UPDATE required_channels "
                "SET title=?, channel_type=?, invite_link=?, username=? "
                "WHERE channel_id=?",
                (title, channel_type, invite_link, username, channel_id)
            )
        else:
            await db.execute(
                "INSERT INTO required_channels "
                "(channel_id, title, channel_type, invite_link, username) "
                "VALUES (?,?,?,?,?)",
                (channel_id, title, channel_type, invite_link, username)
            )
        await db.commit()


async def remove_required_channel(channel_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM required_channels WHERE channel_id=?", (channel_id,))
        await db.commit()


# ─── SUPPORT ──────────────────────────────────────────────────

async def save_support_ticket(user_id: int, message_tg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO support_tickets (user_id, message_tg_id) VALUES (?,?)",
            (user_id, message_tg_id)
        )
        await db.commit()
        return cur.lastrowid


async def get_ticket_by_message(message_tg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM support_tickets WHERE message_tg_id=?", (message_tg_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None
