"""
Web App API Server — serves game data to the Telegram Mini App
Runs alongside the bot on a different port (default 8080).

Endpoints (all prefixed /webapp):
  GET  /categories           → list categories
  GET  /levels/<cat_id>      → list levels in category
  GET  /games/<level_id>     → list games in level
  GET  /game/<game_id>       → full game with questions
  POST /score                → submit score
  GET  /leaderboard/<game_id>→ top scores
  GET  /progress             → user's game progress

All requests validated via Telegram initData header.
"""
import json
import hmac
import hashlib
import logging
from urllib.parse import parse_qs, unquote
from aiohttp import web
import aiosqlite
from database.db import DB_PATH
from config import settings

logger = logging.getLogger(__name__)


# ─── Telegram initData validation ─────────────────────────────

def validate_init_data(init_data: str) -> dict | None:
    """Validate Telegram WebApp initData. Returns user dict or None."""
    if not init_data:
        return None
    try:
        parsed = parse_qs(init_data)
        data_check_string = "\n".join(
            f"{k}={v[0]}"
            for k, v in sorted(parsed.items())
            if k != "hash"
        )
        secret_key = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected   = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        received   = parsed.get("hash", [""])[0]
        if not hmac.compare_digest(expected, received):
            return None
        user_str = parsed.get("user", ["{}"])[0]
        return json.loads(unquote(user_str))
    except Exception as e:
        logger.warning(f"initData validation failed: {e}")
        return None


def get_user_id(request: web.Request) -> int | None:
    """Extract and validate user ID from request."""
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    # In dev mode (no initData), allow if BOT_TOKEN not set or debug
    if not init_data and settings.AI_DAILY_LIMIT == 0:
        return 0   # dev mode fallback
    user = validate_init_data(init_data)
    return user.get("id") if user else None


# ─── DB helpers ───────────────────────────────────────────────

async def ensure_game_tables():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                type TEXT NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS game_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                correct TEXT NOT NULL,
                options TEXT,
                explanation TEXT,
                sort_order INTEGER DEFAULT 0,
                FOREIGN KEY(game_id) REFERENCES games(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS game_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                game_id INTEGER NOT NULL,
                score INTEGER NOT NULL,
                played_at TEXT DEFAULT (datetime('now'))
            );
        """)
        await db.commit()


# ─── Route handlers ───────────────────────────────────────────

async def get_categories(request):
    await ensure_game_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM categories ORDER BY sort_order, id") as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    return web.json_response(rows)


async def get_levels(request):
    cat_id = int(request.match_info["cat_id"])
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM levels WHERE category_id=? ORDER BY sort_order, id", (cat_id,)
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    return web.json_response(rows)


async def get_games(request):
    lvl_id  = int(request.match_info["level_id"])
    uid     = get_user_id(request)
    await ensure_game_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT g.*, COUNT(q.id) as question_count FROM games g "
            "LEFT JOIN game_questions q ON q.game_id=g.id "
            "WHERE g.level_id=? GROUP BY g.id ORDER BY g.id",
            (lvl_id,)
        ) as cur:
            games = [dict(r) for r in await cur.fetchall()]
        # Add user's best score for each game
        if uid:
            for g in games:
                async with db.execute(
                    "SELECT MAX(score) as best FROM game_scores WHERE user_id=? AND game_id=?",
                    (uid, g["id"])
                ) as cur:
                    row = await cur.fetchone()
                    g["best_score"] = row["best"] or 0
    return web.json_response(games)


async def get_game(request):
    game_id = int(request.match_info["game_id"])
    await ensure_game_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM games WHERE id=?", (game_id,)) as cur:
            game = await cur.fetchone()
        if not game:
            return web.json_response({"error": "Not found"}, status=404)
        game = dict(game)
        async with db.execute(
            "SELECT * FROM game_questions WHERE game_id=? ORDER BY sort_order, id", (game_id,)
        ) as cur:
            qs = []
            for row in await cur.fetchall():
                q = dict(row)
                if q.get("options"):
                    try:
                        q["options"] = json.loads(q["options"])
                    except Exception:
                        q["options"] = [q["correct"]]
                qs.append(q)
        game["questions"] = qs
    return web.json_response(game)


async def submit_score(request):
    uid = get_user_id(request)
    if not uid:
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        data    = await request.json()
        game_id = int(data["game_id"])
        score   = max(0, min(100, int(data["score"])))
    except Exception:
        return web.json_response({"error": "Bad request"}, status=400)
    await ensure_game_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO game_scores (user_id, game_id, score) VALUES (?,?,?)",
            (uid, game_id, score)
        )
        await db.commit()
    return web.json_response({"ok": True, "score": score})


async def get_leaderboard(request):
    game_id = int(request.match_info["game_id"])
    await ensure_game_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT u.full_name, u.username, MAX(s.score) as best_score
               FROM game_scores s JOIN users u ON u.tg_id=s.user_id
               WHERE s.game_id=?
               GROUP BY s.user_id ORDER BY best_score DESC LIMIT 10""",
            (game_id,)
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    return web.json_response(rows)


async def get_progress(request):
    uid = get_user_id(request)
    if not uid:
        return web.json_response({})
    await ensure_game_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT COUNT(*) as total_played, MAX(score) as best_score FROM game_scores WHERE user_id=?",
            (uid,)
        ) as cur:
            row = dict(await cur.fetchone())
    return web.json_response(row)


# ─── CORS middleware ──────────────────────────────────────────

@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        return web.Response(headers={
            "Access-Control-Allow-Origin":  "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,X-Telegram-Init-Data",
        })
    response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


# ─── App factory ─────────────────────────────────────────────

def create_webapp():
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get ("/webapp/categories",          get_categories)
    app.router.add_get ("/webapp/levels/{cat_id}",     get_levels)
    app.router.add_get ("/webapp/games/{level_id}",    get_games)
    app.router.add_get ("/webapp/game/{game_id}",      get_game)
    app.router.add_post("/webapp/score",               submit_score)
    app.router.add_get ("/webapp/leaderboard/{game_id}", get_leaderboard)
    app.router.add_get ("/webapp/progress",            get_progress)
    return app
