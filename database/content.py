import aiosqlite
from database.db import DB_PATH


# ─── CATEGORIES ───────────────────────────────────────────────

async def get_categories():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM categories ORDER BY sort_order, id") as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_category(cat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM categories WHERE id=?", (cat_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def add_category(name: str, description: str = None, emoji: str = "📚", is_vip: int = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO categories (name, description, emoji, is_vip) VALUES (?,?,?,?)",
            (name, description, emoji, is_vip)
        )
        await db.commit()
        return cur.lastrowid


async def delete_category(cat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM categories WHERE id=?", (cat_id,))
        await db.commit()


async def update_category(cat_id: int, **kwargs):
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [cat_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE categories SET {sets} WHERE id=?", vals)
        await db.commit()


# ─── LEVELS ───────────────────────────────────────────────────

async def get_levels(category_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM levels WHERE category_id=? ORDER BY sort_order, id",
            (category_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_level(level_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM levels WHERE id=?", (level_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def add_level(category_id: int, name: str, description: str = None, emoji: str = "📖", is_vip: int = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO levels (category_id, name, description, emoji, is_vip) VALUES (?,?,?,?,?)",
            (category_id, name, description, emoji, is_vip)
        )
        await db.commit()
        return cur.lastrowid


async def delete_level(level_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM levels WHERE id=?", (level_id,))
        await db.commit()


async def update_level(level_id: int, **kwargs):
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [level_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE levels SET {sets} WHERE id=?", vals)
        await db.commit()


# ─── LESSONS ──────────────────────────────────────────────────

async def get_lessons(level_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM lessons WHERE level_id=? ORDER BY sort_order, id",
            (level_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_lesson(lesson_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM lessons WHERE id=?", (lesson_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def add_lesson(level_id: int, title: str, description: str = None,
                     content_type: str = "forward", file_id: str = None,
                     message_id: int = None, channel_id: str = None,
                     unlock_code: str = None, is_free: int = 0, is_vip: int = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO lessons
               (level_id, title, description, content_type, file_id, message_id, channel_id, unlock_code, is_free, is_vip)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (level_id, title, description, content_type, file_id, message_id, channel_id, unlock_code, is_free, is_vip)
        )
        await db.commit()
        return cur.lastrowid


async def delete_lesson(lesson_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM lessons WHERE id=?", (lesson_id,))
        await db.commit()


async def update_lesson(lesson_id: int, **kwargs):
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [lesson_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE lessons SET {sets} WHERE id=?", vals)
        await db.commit()


async def increment_view(lesson_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE lessons SET view_count = view_count + 1 WHERE id=?", (lesson_id,))
        await db.commit()


async def search_lessons(query: str, limit: int = 20):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        pattern = f"%{query}%"
        async with db.execute(
            """SELECT l.*, lv.name as level_name, c.name as category_name
               FROM lessons l
               JOIN levels lv ON l.level_id = lv.id
               JOIN categories c ON lv.category_id = c.id
               WHERE l.title LIKE ? OR l.description LIKE ?
               ORDER BY l.view_count DESC LIMIT ?""",
            (pattern, pattern, limit)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ─── USER LESSON ACCESS ───────────────────────────────────────

async def is_lesson_unlocked(user_id: int, lesson_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM user_lessons WHERE user_id=? AND lesson_id=?",
            (user_id, lesson_id)
        ) as cur:
            return await cur.fetchone() is not None


async def unlock_lesson(user_id: int, lesson_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_lessons (user_id, lesson_id) VALUES (?,?)",
            (user_id, lesson_id)
        )
        await db.commit()


async def get_user_unlocked_lessons(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT l.*, ul.unlocked_at FROM lessons l
               JOIN user_lessons ul ON l.id = ul.lesson_id
               WHERE ul.user_id=? ORDER BY ul.unlocked_at DESC""",
            (user_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ─── CODE ATTEMPTS ────────────────────────────────────────────

async def get_attempts(user_id: int, lesson_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM code_attempts WHERE user_id=? AND lesson_id=?",
            (user_id, lesson_id)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def record_wrong_attempt(user_id: int, lesson_id: int, max_attempts: int, lockout_minutes: int):
    from datetime import datetime, timedelta
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM code_attempts WHERE user_id=? AND lesson_id=?",
            (user_id, lesson_id)
        ) as cur:
            row = await cur.fetchone()

        now = datetime.now()
        if row:
            attempts = row["attempts"] + 1
            locked_until = None
            if attempts >= max_attempts:
                locked_until = (now + timedelta(minutes=lockout_minutes)).isoformat()
            await db.execute(
                "UPDATE code_attempts SET attempts=?, locked_until=?, updated_at=? WHERE user_id=? AND lesson_id=?",
                (attempts, locked_until, now.isoformat(), user_id, lesson_id)
            )
        else:
            await db.execute(
                "INSERT INTO code_attempts (user_id, lesson_id, attempts) VALUES (?,?,1)",
                (user_id, lesson_id)
            )
        await db.commit()


async def reset_attempts(user_id: int, lesson_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM code_attempts WHERE user_id=? AND lesson_id=?",
            (user_id, lesson_id)
        )
        await db.commit()


async def get_content_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) as c FROM categories") as cur:
            cats = (await cur.fetchone())["c"]
        async with db.execute("SELECT COUNT(*) as c FROM levels") as cur:
            lvls = (await cur.fetchone())["c"]
        async with db.execute("SELECT COUNT(*) as c FROM lessons") as cur:
            less = (await cur.fetchone())["c"]
        async with db.execute("SELECT SUM(view_count) as v FROM lessons") as cur:
            views = (await cur.fetchone())["v"] or 0
        return {"categories": cats, "levels": lvls, "lessons": less, "total_views": views}
