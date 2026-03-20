"""
Web App API + Static File Server
─────────────────────────────────
Serves BOTH:
  • /webapp/*  → JSON API for game data
  • /*         → Static files from webapp/dist/ folder

Railway auto-assigns PORT env var — bot uses that same port.
No separate port, no Netlify needed.
"""
import json
import hmac
import hashlib
import logging
import os
from pathlib import Path
from urllib.parse import parse_qs, unquote
from aiohttp import web
import aiosqlite
from database.db import DB_PATH
from config import settings

logger = logging.getLogger(__name__)

# Path to built webapp files (relative to main.py)
DIST_DIR = Path(__file__).parent / "webapp" / "dist"

CORS_HEADERS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Telegram-Init-Data",
}


# ─── Auth ─────────────────────────────────────────────────────

def get_user_id(request: web.Request) -> int:
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if not init_data:
        return 0  # anonymous — still allowed to browse
    try:
        parsed = parse_qs(init_data, keep_blank_values=True)
        received_hash = parsed.pop("hash", [""])[0]
        data_check = "\n".join(f"{k}={v[0]}" for k, v in sorted(parsed.items()))
        secret = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, received_hash):
            return 0
        user_str = parsed.get("user", ["{}"])[0]
        user = json.loads(unquote(user_str))
        return user.get("id") or 0
    except Exception:
        return 0


# ─── DB ───────────────────────────────────────────────────────

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


# ─── API Routes ───────────────────────────────────────────────

async def health(request):
    return web.json_response({"status": "ok", "bot": "LearnBot"})


async def api_categories(request):
    await ensure_game_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM categories ORDER BY sort_order, id") as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    return web.json_response(rows)


async def api_levels(request):
    cat_id = int(request.match_info["cat_id"])
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM levels WHERE category_id=? ORDER BY sort_order, id", (cat_id,)
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    return web.json_response(rows)


async def api_games(request):
    lvl_id = int(request.match_info["level_id"])
    uid    = get_user_id(request)
    await ensure_game_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT g.*, COUNT(q.id) as question_count
               FROM games g
               LEFT JOIN game_questions q ON q.game_id=g.id
               WHERE g.level_id=?
               GROUP BY g.id ORDER BY g.id""",
            (lvl_id,)
        ) as cur:
            games = [dict(r) for r in await cur.fetchall()]
        for g in games:
            g["best_score"] = 0
            if uid:
                async with db.execute(
                    "SELECT MAX(score) as best FROM game_scores WHERE user_id=? AND game_id=?",
                    (uid, g["id"])
                ) as cur2:
                    row = await cur2.fetchone()
                    g["best_score"] = (row["best"] or 0) if row else 0
    return web.json_response(games)


async def api_game(request):
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
            "SELECT * FROM game_questions WHERE game_id=? ORDER BY sort_order, id",
            (game_id,)
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


async def api_score(request):
    uid = get_user_id(request)
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


async def api_leaderboard(request):
    game_id = int(request.match_info["game_id"])
    await ensure_game_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT u.full_name, u.username, MAX(s.score) as best_score
               FROM game_scores s JOIN users u ON u.tg_id=s.user_id
               WHERE s.game_id=? GROUP BY s.user_id ORDER BY best_score DESC LIMIT 10""",
            (game_id,)
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    return web.json_response(rows)


async def api_progress(request):
    uid = get_user_id(request)
    if not uid:
        return web.json_response({"total_played": 0, "best_score": 0})
    await ensure_game_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT COUNT(*) as total_played, MAX(score) as best_score "
            "FROM game_scores WHERE user_id=?", (uid,)
        ) as cur:
            row = dict(await cur.fetchone())
    return web.json_response(row)


# ─── Static file server (serves built React app) ──────────────

async def serve_static(request):
    """Serve webapp/dist files. Falls back to index.html for SPA routing."""
    if not DIST_DIR.exists():
        return web.Response(
            text=(
                "<h2>Web App not built yet</h2>"
                "<p>Run <code>npm run build</code> in the learnbot-webapp folder "
                "and copy the <code>dist/</code> folder to <code>learnbot/webapp/dist/</code></p>"
            ),
            content_type="text/html",
            status=200
        )

    path = request.match_info.get("path", "")
    file_path = DIST_DIR / path if path else DIST_DIR / "index.html"

    # Security: prevent path traversal
    try:
        file_path.resolve().relative_to(DIST_DIR.resolve())
    except ValueError:
        raise web.HTTPForbidden()

    if not file_path.exists() or file_path.is_dir():
        file_path = DIST_DIR / "index.html"  # SPA fallback

    return web.FileResponse(file_path)


# ─── CORS middleware ──────────────────────────────────────────

@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=CORS_HEADERS)
    try:
        response = await handler(request)
    except web.HTTPException as e:
        raise
    except Exception as e:
        logger.error(f"API error on {request.path}: {e}")
        response = web.json_response({"error": "Server error"}, status=500)
    for k, v in CORS_HEADERS.items():
        response.headers[k] = v
    return response


# ─── App factory ─────────────────────────────────────────────

def create_webapp():
    app = web.Application(middlewares=[cors_middleware])

    # API routes
    app.router.add_get ("/api/health",                   health)
    app.router.add_get ("/webapp/categories",             api_categories)
    app.router.add_get ("/webapp/levels/{cat_id}",        api_levels)
    app.router.add_get ("/webapp/games/{level_id}",       api_games)
    app.router.add_get ("/webapp/game/{game_id}",         api_game)
    app.router.add_post("/webapp/score",                  api_score)
    app.router.add_get ("/webapp/leaderboard/{game_id}",  api_leaderboard)
    app.router.add_get ("/webapp/progress",               api_progress)

    # Static files (React app)
    app.router.add_get ("/",                              serve_static)
    app.router.add_get ("/{path:.*}",                     serve_static)

    return app
