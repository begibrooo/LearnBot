import aiosqlite
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

# Railway provides a /data volume OR we fall back to current dir
# Set DATA_DIR env var on Railway to /data for persistence
DATA_DIR = os.environ.get("DATA_DIR", ".")
DB_PATH  = os.path.join(DATA_DIR, "learnbot.db")

# Make sure the data directory exists
os.makedirs(DATA_DIR, exist_ok=True)


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                tg_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                full_name TEXT,
                is_vip INTEGER DEFAULT 0,
                vip_expires_at TEXT,
                vip_lesson_limit INTEGER DEFAULT 0,
                vip_lessons_used INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                free_passes INTEGER DEFAULT 0,
                invites_count INTEGER DEFAULT 0,
                referred_by INTEGER,
                streak_days INTEGER DEFAULT 0,
                last_checkin TEXT,
                total_checkins INTEGER DEFAULT 0,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                last_seen TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                emoji TEXT DEFAULT '📚',
                is_vip INTEGER DEFAULT 0,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS levels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                emoji TEXT DEFAULT '📖',
                is_vip INTEGER DEFAULT 0,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                content_type TEXT DEFAULT 'forward',
                file_id TEXT,
                message_id INTEGER,
                channel_id TEXT,
                unlock_code TEXT,
                is_free INTEGER DEFAULT 0,
                is_vip INTEGER DEFAULT 0,
                view_count INTEGER DEFAULT 0,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(level_id) REFERENCES levels(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                lesson_id INTEGER NOT NULL,
                unlocked_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, lesson_id)
            );

            CREATE TABLE IF NOT EXISTS promo_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                promo_type TEXT NOT NULL,
                free_passes INTEGER DEFAULT 0,
                lesson_id INTEGER,
                file_id TEXT,
                file_type TEXT,
                file_caption TEXT,
                max_uses INTEGER,
                uses_count INTEGER DEFAULT 0,
                expires_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS promo_uses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                promo_id INTEGER NOT NULL,
                used_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, promo_id)
            );

            CREATE TABLE IF NOT EXISTS code_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                lesson_id INTEGER NOT NULL,
                attempts INTEGER DEFAULT 0,
                locked_until TEXT,
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, lesson_id)
            );

            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message_tg_id INTEGER,
                status TEXT DEFAULT 'open',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS required_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT UNIQUE NOT NULL,
                title TEXT,
                channel_type TEXT DEFAULT 'public',
                invite_link TEXT,
                username TEXT,
                added_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                data TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS quizzes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                option_a TEXT NOT NULL,
                option_b TEXT NOT NULL,
                option_c TEXT NOT NULL,
                option_d TEXT NOT NULL,
                correct TEXT NOT NULL,
                explanation TEXT,
                lesson_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS quiz_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                quiz_id INTEGER NOT NULL,
                answer TEXT NOT NULL,
                is_correct INTEGER NOT NULL,
                answered_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, quiz_id)
            );

            CREATE TABLE IF NOT EXISTS lesson_ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                lesson_id INTEGER NOT NULL,
                rating INTEGER NOT NULL,
                rated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, lesson_id)
            );

            CREATE TABLE IF NOT EXISTS vip_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                reason TEXT,
                granted_by INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS user_badges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                badge_key TEXT NOT NULL,
                earned_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, badge_key)
            );

            CREATE TABLE IF NOT EXISTS daily_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                challenge_date TEXT UNIQUE NOT NULL,
                type TEXT NOT NULL,
                description TEXT NOT NULL,
                target_value INTEGER DEFAULT 1,
                reward_passes INTEGER DEFAULT 1,
                winner_limit INTEGER DEFAULT 10,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS challenge_completions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                challenge_id INTEGER NOT NULL,
                completed_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, challenge_id)
            );
        """)
        await db.commit()
        logger.info(f"Database initialized at {DB_PATH}")


async def migrate_db():
    """Safe ALTER TABLE migrations for new columns."""
    cols = [
        ("users", "vip_expires_at",    "TEXT"),
        ("users", "vip_lesson_limit",  "INTEGER DEFAULT 0"),
        ("users", "vip_lessons_used",  "INTEGER DEFAULT 0"),
        ("users", "streak_days",       "INTEGER DEFAULT 0"),
        ("users", "last_checkin",      "TEXT"),
        ("users", "total_checkins",    "INTEGER DEFAULT 0"),
        ("users", "notes",             "TEXT"),
        ("required_channels", "channel_type",  "TEXT DEFAULT 'public'"),
        ("required_channels", "invite_link",   "TEXT"),
        ("required_channels", "username",      "TEXT"),
    ]
    async with aiosqlite.connect(DB_PATH) as db:
        for table, col, dfn in cols:
            try:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {dfn}")
                await db.commit()
            except Exception:
                pass
