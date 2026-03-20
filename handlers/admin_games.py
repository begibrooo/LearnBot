"""
Admin Games Management
Admin can create/delete games linked to lessons/levels.
Games are played in the Telegram Mini App.

Game types:
  quiz      — multiple choice
  flashcard — flip to reveal answer
  match     — connect pairs
  fill      — fill in the blank
"""
import json
import logging
import aiosqlite
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import settings
from database.db import DB_PATH
from keyboards.admin import back_admin_kb
from keyboards.user import cancel_kb

router = Router()
logger = logging.getLogger(__name__)


def is_admin(uid): return uid in settings.admin_id_list


# ─── DB helpers ───────────────────────────────────────────────

async def ensure_tables():
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
        """)
        await db.commit()


async def get_all_games():
    await ensure_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT g.*, COUNT(q.id) as q_count,
               l.name as level_name, c.name as cat_name
               FROM games g
               LEFT JOIN game_questions q ON q.game_id=g.id
               LEFT JOIN levels l ON l.id=g.level_id
               LEFT JOIN categories c ON c.id=l.category_id
               GROUP BY g.id ORDER BY g.id DESC"""
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def delete_game(game_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM games WHERE id=?", (game_id,))
        await db.commit()


async def create_game(level_id: int, title: str, gtype: str, description: str = None) -> int:
    await ensure_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO games (level_id, title, type, description) VALUES (?,?,?,?)",
            (level_id, title, gtype, description)
        )
        await db.commit()
        return cur.lastrowid


async def add_question(game_id: int, question: str, correct: str, options: list = None, explanation: str = None):
    await ensure_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO game_questions (game_id, question, correct, options, explanation) VALUES (?,?,?,?,?)",
            (game_id, question, correct, json.dumps(options) if options else None, explanation)
        )
        await db.commit()


# ─── Keyboards ────────────────────────────────────────────────

def games_list_kb(games: list) -> InlineKeyboardMarkup:
    rows = []
    TYPE_ICONS = {"quiz":"🧠","flashcard":"🃏","match":"🔗","fill":"✏️"}
    for g in games:
        icon = TYPE_ICONS.get(g["type"], "🎮")
        rows.append([
            InlineKeyboardButton(
                text=f"{icon} {g['title']} ({g['q_count']}q)",
                callback_data=f"game_detail:{g['id']}"
            ),
            InlineKeyboardButton(text="🗑", callback_data=f"game_del:{g['id']}"),
        ])
    rows.append([InlineKeyboardButton(text="➕ Create Game", callback_data="game_create")])
    rows.append([InlineKeyboardButton(text="◀️ Back",        callback_data="adm:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def game_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 Quiz (multiple choice)", callback_data="gtype:quiz")],
        [InlineKeyboardButton(text="🃏 Flashcards (flip cards)", callback_data="gtype:flashcard")],
        [InlineKeyboardButton(text="🔗 Match pairs",             callback_data="gtype:match")],
        [InlineKeyboardButton(text="✏️ Fill in the blank",       callback_data="gtype:fill")],
        [InlineKeyboardButton(text="❌ Cancel",                  callback_data="adm:games")],
    ])


# ─── Admin panel entry ────────────────────────────────────────

@router.callback_query(F.data == "adm:games")
async def adm_games(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    games = await get_all_games()
    await call.message.edit_text(
        f"🎮 <b>Games Management</b>\n\n"
        f"Total games: <b>{len(games)}</b>\n\n"
        f"Games are played in the Telegram Mini App.",
        reply_markup=games_list_kb(games)
    )
    await call.answer()


@router.callback_query(F.data.startswith("game_detail:"))
async def game_detail(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    game_id = int(call.data.split(":")[1])
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM games WHERE id=?", (game_id,)) as cur:
            g = await cur.fetchone()
        async with db.execute(
            "SELECT COUNT(*) as c FROM game_questions WHERE game_id=?", (game_id,)
        ) as cur:
            q_count = (await cur.fetchone())["c"]
    if not g: await call.answer("Not found."); return
    g = dict(g)
    await call.message.edit_text(
        f"🎮 <b>{g['title']}</b>\n\n"
        f"Type: {g['type']}\n"
        f"Questions: <b>{q_count}</b>\n"
        f"Level ID: {g['level_id']}\n"
        f"Desc: {g.get('description') or '—'}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Add Question", callback_data=f"gq_add:{game_id}")],
            [InlineKeyboardButton(text="📋 View Questions", callback_data=f"gq_list:{game_id}")],
            [InlineKeyboardButton(text="🗑 Delete Game",   callback_data=f"game_del:{game_id}")],
            [InlineKeyboardButton(text="◀️ Back",          callback_data="adm:games")],
        ])
    )
    await call.answer()


@router.callback_query(F.data.startswith("game_del:"))
async def game_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    game_id = int(call.data.split(":")[1])
    await delete_game(game_id)
    await call.answer("✅ Game deleted.", show_alert=True)
    games = await get_all_games()
    await call.message.edit_text(
        f"🎮 <b>Games</b>  ({len(games)} total)",
        reply_markup=games_list_kb(games)
    )


@router.callback_query(F.data.startswith("gq_list:"))
async def gq_list(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    game_id = int(call.data.split(":")[1])
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM game_questions WHERE game_id=? ORDER BY sort_order,id", (game_id,)
        ) as cur:
            qs = [dict(r) for r in await cur.fetchall()]
    if not qs:
        await call.answer("No questions yet.", show_alert=True); return
    text = f"📋 <b>Questions ({len(qs)})</b>\n\n"
    for i, q in enumerate(qs, 1):
        text += f"{i}. {q['question'][:50]}...\n   ✔️ {q['correct'][:30]}\n\n"
    await call.message.edit_text(
        text[:3000],
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="➕ Add Question", callback_data=f"gq_add:{game_id}"),
            InlineKeyboardButton(text="◀️ Back",         callback_data=f"game_detail:{game_id}"),
        ]])
    )
    await call.answer()


# ─── Create game wizard ───────────────────────────────────────

class GameCreateState(StatesGroup):
    level_id    = State()
    title       = State()
    gtype       = State()
    description = State()


class QuestionAddState(StatesGroup):
    question    = State()
    correct     = State()
    options     = State()   # for quiz type
    explanation = State()
    more        = State()


@router.callback_query(F.data == "game_create")
async def game_create_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(GameCreateState.level_id)
    await call.message.edit_text(
        "🎮 <b>Create Game — Step 1/4</b>\n\n"
        "Send the <b>Level ID</b> this game belongs to:\n\n"
        "<i>Tip: use 📋 Levels in Content panel to find IDs.</i>",
        reply_markup=cancel_kb()
    )
    await call.answer()


@router.message(GameCreateState.level_id)
async def gc_level(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try:
        lvl_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Must be a number."); return
    await state.update_data(level_id=lvl_id)
    await state.set_state(GameCreateState.title)
    await message.answer("🎮 <b>Step 2/4</b> — Enter the <b>game title</b>:", reply_markup=cancel_kb())


@router.message(GameCreateState.title)
async def gc_title(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.update_data(title=message.text.strip())
    await state.set_state(GameCreateState.gtype)
    await message.answer("🎮 <b>Step 3/4</b> — Choose game <b>type</b>:", reply_markup=game_type_kb())


@router.callback_query(F.data.startswith("gtype:"))
async def gc_type(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    gtype = call.data.split(":")[1]
    await state.update_data(gtype=gtype)
    await state.set_state(GameCreateState.description)
    await call.message.edit_text(
        "🎮 <b>Step 4/4</b> — Enter a <b>description</b> (or - to skip):",
        reply_markup=cancel_kb()
    )
    await call.answer()


@router.message(GameCreateState.description)
async def gc_desc(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    desc = None if message.text.strip() == "-" else message.text.strip()
    data = await state.get_data()
    await state.clear()
    game_id = await create_game(data["level_id"], data["title"], data["gtype"], desc)
    await message.answer(
        f"✅ <b>Game created!</b>\n\n"
        f"🎮 <b>{data['title']}</b>\n"
        f"Type: {data['gtype']}\n"
        f"ID: <code>{game_id}</code>\n\n"
        f"Now add questions to it:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="➕ Add Questions", callback_data=f"gq_add:{game_id}"),
            InlineKeyboardButton(text="📋 All Games",     callback_data="adm:games"),
        ]])
    )


# ─── Add question wizard ──────────────────────────────────────

@router.callback_query(F.data.startswith("gq_add:"))
async def gq_add_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    game_id = int(call.data.split(":")[1])

    # Check game type to know what to ask
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT type FROM games WHERE id=?", (game_id,)) as cur:
            row = await cur.fetchone()
    if not row: await call.answer("Game not found."); return
    gtype = row["type"]

    await state.update_data(game_id=game_id, gtype=gtype)
    await state.set_state(QuestionAddState.question)
    prompts = {
        "quiz":      "Enter the <b>question</b>:",
        "flashcard": "Enter the <b>front</b> of the card (question/term):",
        "match":     "Enter the <b>left side</b> (term):",
        "fill":      "Enter the sentence with <b>___</b> for the blank:\n\n<i>Example: The capital of France is ___</i>",
    }
    await call.message.edit_text(
        f"➕ <b>Add Question ({gtype})</b>\n\n{prompts.get(gtype, 'Enter question:')}",
        reply_markup=cancel_kb()
    )
    await call.answer()


@router.message(QuestionAddState.question)
async def qa_question(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.update_data(question=message.text.strip())
    data = await state.get_data()
    gtype = data.get("gtype")
    await state.set_state(QuestionAddState.correct)
    prompts = {
        "quiz":      "Enter the <b>correct answer</b>:",
        "flashcard": "Enter the <b>back</b> of the card (answer/definition):",
        "match":     "Enter the <b>right side</b> (definition/pair):",
        "fill":      "Enter the <b>correct word</b> that fills the blank:",
    }
    await message.answer(prompts.get(gtype, "Enter correct answer:"), reply_markup=cancel_kb())


@router.message(QuestionAddState.correct)
async def qa_correct(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.update_data(correct=message.text.strip())
    data = await state.get_data()
    gtype = data.get("gtype")

    if gtype == "quiz":
        await state.set_state(QuestionAddState.options)
        await message.answer(
            "Enter <b>wrong options</b> (3 options, one per line):\n\n"
            "<i>These will be shown alongside the correct answer.</i>",
            reply_markup=cancel_kb()
        )
    else:
        await state.set_state(QuestionAddState.explanation)
        await message.answer("Enter an <b>explanation</b> (or - to skip):", reply_markup=cancel_kb())


@router.message(QuestionAddState.options)
async def qa_options(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    wrong = [o.strip() for o in message.text.strip().splitlines() if o.strip()][:3]
    await state.update_data(wrong_options=wrong)
    await state.set_state(QuestionAddState.explanation)
    await message.answer("Enter an <b>explanation</b> (or - to skip):", reply_markup=cancel_kb())


@router.message(QuestionAddState.explanation)
async def qa_explanation(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    explanation = None if message.text.strip() == "-" else message.text.strip()
    data = await state.get_data()
    await state.clear()

    game_id  = data["game_id"]
    gtype    = data["gtype"]
    question = data["question"]
    correct  = data["correct"]
    wrong    = data.get("wrong_options", [])

    # Build options list for quiz (shuffle correct + wrong)
    options = None
    if gtype == "quiz":
        import random
        opts = wrong + [correct]
        random.shuffle(opts)
        options = opts

    await add_question(game_id, question, correct, options, explanation)

    # Count questions
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT COUNT(*) as c FROM game_questions WHERE game_id=?", (game_id,)
        ) as cur:
            count = (await cur.fetchone())["c"]

    await message.answer(
        f"✅ <b>Question added!</b>  ({count} total in this game)\n\n"
        f"Q: {question[:60]}\n"
        f"✔️ {correct[:40]}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="➕ Add Another", callback_data=f"gq_add:{game_id}"),
            InlineKeyboardButton(text="📋 View Game",   callback_data=f"game_detail:{game_id}"),
            InlineKeyboardButton(text="🎮 All Games",   callback_data="adm:games"),
        ]])
    )
