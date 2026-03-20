import aiosqlite
from datetime import datetime
from database.db import DB_PATH


async def get_or_create_user(tg_id: int, username: str = None, full_name: str = None, referred_by: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)) as cur:
            user = await cur.fetchone()
        if user:
            await db.execute(
                "UPDATE users SET username=?, full_name=?, last_seen=? WHERE tg_id=?",
                (username, full_name, datetime.now().isoformat(), tg_id)
            )
            await db.commit()
        else:
            await db.execute(
                "INSERT INTO users (tg_id, username, full_name, referred_by) VALUES (?,?,?,?)",
                (tg_id, username, full_name, referred_by)
            )
            await db.commit()
        async with db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)) as cur:
            return dict(await cur.fetchone())


async def get_user(tg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def update_user(tg_id: int, **kwargs):
    if not kwargs:
        return
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [tg_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {sets} WHERE tg_id=?", vals)
        await db.commit()


async def add_free_pass(tg_id: int, amount: int = 1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET free_passes=free_passes+? WHERE tg_id=?", (amount, tg_id))
        await db.commit()


async def use_free_pass(tg_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT free_passes FROM users WHERE tg_id=?", (tg_id,)) as cur:
            row = await cur.fetchone()
        if not row or row["free_passes"] < 1:
            return False
        await db.execute("UPDATE users SET free_passes=free_passes-1 WHERE tg_id=?", (tg_id,))
        await db.commit()
        return True


async def increment_invites(tg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET invites_count=invites_count+1 WHERE tg_id=?", (tg_id,))
        await db.commit()


# ─── VIP WITH EXPIRY & LESSON LIMIT ───────────────────────────

async def grant_vip(tg_id: int, lesson_limit: int = 0, expires_at: str = None, granted_by: int = None, reason: str = None):
    """
    lesson_limit: 0 = unlimited, >0 = VIP expires after N lessons
    expires_at: ISO datetime string or None = no time expiry
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET is_vip=1, vip_expires_at=?, vip_lesson_limit=?, vip_lessons_used=0 WHERE tg_id=?",
            (expires_at, lesson_limit, tg_id)
        )
        await db.execute(
            "INSERT INTO vip_log (user_id, action, reason, granted_by) VALUES (?,?,?,?)",
            (tg_id, "grant", reason, granted_by)
        )
        await db.commit()


async def revoke_vip(tg_id: int, reason: str = None, revoked_by: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET is_vip=0, vip_expires_at=NULL, vip_lesson_limit=0, vip_lessons_used=0 WHERE tg_id=?",
            (tg_id,)
        )
        await db.execute(
            "INSERT INTO vip_log (user_id, action, reason, granted_by) VALUES (?,?,?,?)",
            (tg_id, "revoke", reason, revoked_by)
        )
        await db.commit()


async def check_vip_validity(tg_id: int) -> bool:
    """Returns True if user's VIP is still valid. Auto-revokes if expired."""
    user = await get_user(tg_id)
    if not user or not user.get("is_vip"):
        return False

    # Time expiry check
    if user.get("vip_expires_at"):
        try:
            exp = datetime.fromisoformat(user["vip_expires_at"])
            if datetime.now() > exp:
                await revoke_vip(tg_id, reason="time_expired")
                return False
        except Exception:
            pass

    # Lesson limit check
    limit = user.get("vip_lesson_limit") or 0
    used  = user.get("vip_lessons_used") or 0
    if limit > 0 and used >= limit:
        await revoke_vip(tg_id, reason="lesson_limit_reached")
        return False

    return True


async def increment_vip_lessons_used(tg_id: int):
    """Call when a VIP user opens a VIP lesson. May auto-revoke."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET vip_lessons_used=vip_lessons_used+1 WHERE tg_id=? AND is_vip=1",
            (tg_id,)
        )
        await db.commit()
    # Check if limit hit
    await check_vip_validity(tg_id)


# ─── USER LISTS ───────────────────────────────────────────────

async def get_all_users_paginated(page: int = 0, per_page: int = 10, filter_vip: bool = False, filter_banned: bool = False) -> tuple[list, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        conditions = []
        if filter_vip:
            conditions.append("is_vip=1")
        if filter_banned:
            conditions.append("is_banned=1")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        async with db.execute(f"SELECT COUNT(*) as c FROM users {where}") as cur:
            total = (await cur.fetchone())["c"]
        offset = page * per_page
        async with db.execute(
            f"SELECT tg_id, username, full_name, is_vip, is_banned, free_passes, "
            f"invites_count, vip_expires_at, vip_lesson_limit, vip_lessons_used, created_at "
            f"FROM users {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
        return rows, total


async def get_vip_users() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT tg_id, username, full_name, vip_expires_at, vip_lesson_limit, vip_lessons_used "
            "FROM users WHERE is_vip=1 ORDER BY created_at DESC"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_leaderboard(limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT tg_id, full_name, username, invites_count FROM users ORDER BY invites_count DESC LIMIT ?",
            (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT tg_id FROM users WHERE is_banned=0") as cur:
            return [r["tg_id"] for r in await cur.fetchall()]


async def get_user_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) as total FROM users") as cur:
            total = (await cur.fetchone())["total"]
        async with db.execute("SELECT COUNT(*) as vip FROM users WHERE is_vip=1") as cur:
            vip = (await cur.fetchone())["vip"]
        async with db.execute("SELECT COUNT(*) as banned FROM users WHERE is_banned=1") as cur:
            banned = (await cur.fetchone())["banned"]
        today = datetime.now().date().isoformat()
        async with db.execute("SELECT COUNT(*) as new FROM users WHERE created_at >= ?", (today,)) as cur:
            new_today = (await cur.fetchone())["new"]
        return {"total": total, "vip": vip, "banned": banned, "new_today": new_today}
