"""
AI Chat Handler — Groq-powered learning assistant
• Conversation history per user (stored in DB, last N messages)
• Chat mode: every message auto-goes to AI until user exits
• /ai <question>  — one-shot question without entering chat mode
• /clear          — reset conversation history
• Daily message limit (configurable via AI_DAILY_LIMIT in .env)
• Typing indicator while AI thinks
• Admin: view usage stats, update system prompt
"""
import logging
import aiosqlite
from datetime import date
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import settings
from database.db import DB_PATH
from utils.ai_client import ask_ai
from keyboards.user import main_menu_kb, cancel_kb

router = Router()
logger = logging.getLogger(__name__)


def is_admin(uid): return uid in settings.admin_id_list


# ─── DB ───────────────────────────────────────────────────────

async def _ensure_tables():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS ai_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS ai_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                usage_date TEXT NOT NULL,
                count INTEGER DEFAULT 0,
                UNIQUE(user_id, usage_date)
            );
        """)
        await db.commit()


async def get_history(user_id: int) -> list[dict]:
    await _ensure_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT role, content FROM ai_history "
            "WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, settings.AI_MAX_HISTORY)
        ) as cur:
            rows = await cur.fetchall()
    msgs = [{"role": "system", "content": settings.AI_SYSTEM_PROMPT}]
    msgs += [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    return msgs


async def save_exchange(user_id: int, user_text: str, ai_text: str):
    await _ensure_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO ai_history (user_id, role, content) VALUES (?,?,?)",
            (user_id, "user", user_text)
        )
        await db.execute(
            "INSERT INTO ai_history (user_id, role, content) VALUES (?,?,?)",
            (user_id, "assistant", ai_text)
        )
        # Trim to max history
        await db.execute(
            """DELETE FROM ai_history WHERE user_id=? AND id NOT IN
               (SELECT id FROM ai_history WHERE user_id=? ORDER BY id DESC LIMIT ?)""",
            (user_id, user_id, settings.AI_MAX_HISTORY)
        )
        await db.commit()


async def clear_history(user_id: int):
    await _ensure_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM ai_history WHERE user_id=?", (user_id,))
        await db.commit()


async def check_limit(user_id: int) -> tuple[bool, int]:
    """Returns (can_use, used_today)."""
    if settings.AI_DAILY_LIMIT <= 0:
        return True, 0
    await _ensure_tables()
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT count FROM ai_usage WHERE user_id=? AND usage_date=?",
            (user_id, today)
        ) as cur:
            row = await cur.fetchone()
    used = row["count"] if row else 0
    return used < settings.AI_DAILY_LIMIT, used


async def increment_usage(user_id: int):
    if settings.AI_DAILY_LIMIT <= 0:
        return
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO ai_usage (user_id, usage_date, count) VALUES (?,?,1)
               ON CONFLICT(user_id, usage_date) DO UPDATE SET count=count+1""",
            (user_id, today)
        )
        await db.commit()


async def get_ai_stats() -> dict:
    await _ensure_tables()
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT COUNT(DISTINCT user_id) as u FROM ai_history"
        ) as cur:
            users = (await cur.fetchone())["u"]
        async with db.execute(
            "SELECT COUNT(*) as m FROM ai_history WHERE role='user'"
        ) as cur:
            total = (await cur.fetchone())["m"]
        async with db.execute(
            "SELECT COALESCE(SUM(count),0) as t FROM ai_usage WHERE usage_date=?",
            (today,)
        ) as cur:
            today_count = (await cur.fetchone())["t"]
    return {"users": users, "total": total, "today": today_count}


# ─── KEYBOARDS ────────────────────────────────────────────────

def chat_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑 Clear History", callback_data="ai:clear"),
            InlineKeyboardButton(text="📊 My Usage",      callback_data="ai:usage"),
        ],
        [InlineKeyboardButton(text="🏠 Exit Chat",        callback_data="ai:exit")],
    ])


# ─── STATES ───────────────────────────────────────────────────

class AIChatState(StatesGroup):
    chatting = State()
    admin_system_prompt = State()


# ─── CORE LOGIC ───────────────────────────────────────────────

async def _process_ai(message: Message, text: str, in_chat_mode: bool = False):
    uid = message.from_user.id

    # Check daily limit
    can_use, used = await check_limit(uid)
    if not can_use:
        await message.answer(
            f"⏳ <b>Daily limit reached!</b>\n\n"
            f"You've used <b>{used}/{settings.AI_DAILY_LIMIT}</b> AI messages today.\n"
            f"Come back tomorrow to continue learning! 🌅",
            reply_markup=chat_kb() if in_chat_mode else None
        )
        return

    # Typing indicator
    await message.bot.send_chat_action(message.chat.id, "typing")

    # Get history → call AI
    history = await get_history(uid)
    history.append({"role": "user", "content": text})

    thinking = await message.answer("🤖 <i>Thinking...</i>")
    reply    = await ask_ai(history)

    # Save exchange + increment
    await save_exchange(uid, text, reply)
    await increment_usage(uid)

    try:
        await thinking.delete()
    except Exception:
        pass

    # Footer: warn when close to limit
    can_use2, used2 = await check_limit(uid)
    remaining = settings.AI_DAILY_LIMIT - used2
    footer = (
        f"\n\n<i>💬 {remaining} messages left today</i>"
        if settings.AI_DAILY_LIMIT > 0 and remaining <= 10
        else ""
    )

    await message.answer(
        f"{reply}{footer}",
        reply_markup=chat_kb() if in_chat_mode else InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🤖 Continue Chat", callback_data="ai:open"),
            InlineKeyboardButton(text="🗑 Clear",         callback_data="ai:clear"),
        ]])
    )


# ─── ENTRY POINTS ─────────────────────────────────────────────

@router.message(Command("ai"))
async def cmd_ai(message: Message, state: FSMContext):
    """
    /ai             → open chat mode
    /ai <question>  → one-shot answer
    """
    text = message.text.strip()
    question = text[3:].strip() if text.startswith("/ai ") else ""

    if question:
        await _process_ai(message, question, in_chat_mode=False)
    else:
        await _open_chat(message, state)


@router.message(F.text == "🤖 AI Chat")
async def btn_ai_chat(message: Message, state: FSMContext):
    await _open_chat(message, state)


@router.callback_query(F.data == "ai:open")
async def cb_ai_open(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await _open_chat(call.message, state)


async def _open_chat(message: Message, state: FSMContext):
    uid = message.from_user.id
    can_use, used = await check_limit(uid)
    history = await get_history(uid)
    msg_count = len([m for m in history if m["role"] == "user"])

    limit_line = (
        f"\n📊 Today: <b>{used}/{settings.AI_DAILY_LIMIT}</b> messages used"
        if settings.AI_DAILY_LIMIT > 0 else ""
    )
    hist_line = (
        f"\n💬 Memory: <b>{msg_count}</b> previous messages"
        if msg_count > 0 else "\n💬 Fresh conversation"
    )

    await state.set_state(AIChatState.chatting)
    await message.answer(
        f"🤖 <b>AI Learning Assistant</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"Powered by <b>Groq × Llama 3.3</b> — fast and free!\n\n"
        f"I remember our full conversation history.\n"
        f"Ask me anything about your lessons! 🎓"
        f"{hist_line}{limit_line}\n\n"
        f"<i>Type your question below:</i>",
        reply_markup=chat_kb()
    )


# ─── CHAT MODE ────────────────────────────────────────────────

@router.message(AIChatState.chatting)
async def chat_message(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Please send a text message.")
        return
    await _process_ai(message, message.text, in_chat_mode=True)


# ─── CALLBACKS ────────────────────────────────────────────────

@router.callback_query(F.data == "ai:clear")
async def cb_clear(call: CallbackQuery):
    await clear_history(call.from_user.id)
    await call.answer("✅ History cleared!", show_alert=True)
    await call.message.edit_text(
        "🗑 <b>Conversation cleared!</b>\n\nSend your first question:",
        reply_markup=chat_kb()
    )


@router.callback_query(F.data == "ai:usage")
async def cb_usage(call: CallbackQuery):
    history  = await get_history(call.from_user.id)
    msg_count = len([m for m in history if m["role"] == "user"])
    _, used  = await check_limit(call.from_user.id)
    limit_txt = f"{used}/{settings.AI_DAILY_LIMIT}" if settings.AI_DAILY_LIMIT > 0 else "Unlimited"
    await call.answer(
        f"💬 Messages in memory: {msg_count}\n"
        f"📊 Used today: {limit_txt}",
        show_alert=True
    )


@router.callback_query(F.data == "ai:exit")
async def cb_exit(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("🏠 <b>Back to main menu</b>", reply_markup=main_menu_kb())
    await call.answer()


@router.message(Command("clearai"))
async def cmd_clear_ai(message: Message):
    await clear_history(message.from_user.id)
    await message.answer("✅ <b>AI conversation history cleared!</b>")


# ─── ADMIN ────────────────────────────────────────────────────

@router.message(Command("ai_stats"))
async def cmd_ai_stats(message: Message):
    if not is_admin(message.from_user.id): return
    s = await get_ai_stats()
    await message.answer(
        f"🤖 <b>AI Usage Stats</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👥 Users who chatted:  <b>{s['users']}</b>\n"
        f"💬 Total messages:     <b>{s['total']}</b>\n"
        f"📅 Messages today:     <b>{s['today']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Provider: <b>{settings.AI_PROVIDER.upper()}</b>\n"
        f"Model:    <b>{settings.ai_model_name}</b>\n"
        f"Limit:    <b>{settings.AI_DAILY_LIMIT or 'Unlimited'}/day</b>"
    )


@router.message(Command("ai_prompt"))
async def cmd_ai_prompt(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.set_state(AIChatState.admin_system_prompt)
    await message.answer(
        f"🤖 <b>Update AI System Prompt</b>\n\n"
        f"Current prompt:\n<i>{settings.AI_SYSTEM_PROMPT}</i>\n\n"
        f"Send new prompt (this affects all users):",
        reply_markup=cancel_kb()
    )


@router.message(AIChatState.admin_system_prompt)
async def save_system_prompt(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.clear()
    # Update at runtime (persists until restart — for permanent change update .env)
    settings.AI_SYSTEM_PROMPT = message.text.strip()
    await message.answer(
        f"✅ <b>System prompt updated!</b>\n\n"
        f"<i>{settings.AI_SYSTEM_PROMPT}</i>\n\n"
        f"<b>Note:</b> This resets on bot restart. Add to .env for permanent change:\n"
        f"<code>AI_SYSTEM_PROMPT=your prompt here</code>"
    )
