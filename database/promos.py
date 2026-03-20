import aiosqlite
from datetime import datetime
from database.db import DB_PATH


async def create_promo(code: str, promo_type: str, free_passes: int = 0,
                       lesson_id: int = None, file_id: str = None,
                       file_type: str = None, file_caption: str = None,
                       max_uses: int = None, expires_at: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO promo_codes
               (code, promo_type, free_passes, lesson_id, file_id, file_type, file_caption, max_uses, expires_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (code.upper(), promo_type, free_passes, lesson_id, file_id, file_type, file_caption, max_uses, expires_at)
        )
        await db.commit()
        return cur.lastrowid


async def get_promo(code: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM promo_codes WHERE code=?", (code.upper(),)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def use_promo(user_id: int, promo_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        # Check already used
        async with db.execute(
            "SELECT 1 FROM promo_uses WHERE user_id=? AND promo_id=?",
            (user_id, promo_id)
        ) as cur:
            if await cur.fetchone():
                return False, "already_used"

        # Increment usage
        await db.execute(
            "UPDATE promo_codes SET uses_count = uses_count + 1 WHERE id=?", (promo_id,)
        )
        await db.execute(
            "INSERT INTO promo_uses (user_id, promo_id) VALUES (?,?)",
            (user_id, promo_id)
        )
        await db.commit()
        return True, "ok"


async def validate_promo(code: str) -> tuple:
    """Returns (promo_dict | None, error_string | None)"""
    promo = await get_promo(code)
    if not promo:
        return None, "not_found"

    now = datetime.now()
    if promo["expires_at"]:
        try:
            exp = datetime.fromisoformat(promo["expires_at"])
            if now > exp:
                return None, "expired"
        except Exception:
            pass

    if promo["max_uses"] is not None and promo["uses_count"] >= promo["max_uses"]:
        return None, "limit_reached"

    return promo, None


async def get_all_promos():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM promo_codes ORDER BY id DESC") as cur:
            return [dict(r) for r in await cur.fetchall()]


async def delete_promo(promo_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM promo_codes WHERE id=?", (promo_id,))
        await db.commit()
