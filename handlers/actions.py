"""
Action Buttons + Styled Background Messages
-------------------------------------------
Produces rich Telegram messages styled like the screenshot:
  • Bold header line
  • Body text
  • Styled action buttons: [  ⚡ Label text 💰  ] [ ↗ ]

Admin commands:
  /action_msg        — wizard to create & send a styled action message
  /test_friday       — manually trigger Friday reward (for testing)
"""
import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import settings
from database.users import get_all_users
from keyboards.user import action_buttons_kb, main_menu_kb, cancel_kb

router = Router()
logger = logging.getLogger(__name__)


def is_admin(uid): return uid in settings.admin_id_list


class ActionMsgState(StatesGroup):
    waiting_title   = State()
    waiting_body    = State()
    waiting_buttons = State()
    confirm         = State()


def _send_options_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Send to myself (preview)", callback_data="actionsend:me")],
        [InlineKeyboardButton(text="📢 Broadcast to ALL users",   callback_data="actionsend:all")],
        [InlineKeyboardButton(text="❌ Cancel",                   callback_data="cancel")],
    ])


def _build_action_text(title: str, body: str) -> str:
    return f"<b>{title}</b>\n\n{body}"


# ─── /action_msg WIZARD ───────────────────────────────────────

@router.message(Command("action_msg"))
async def action_msg_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.set_state(ActionMsgState.waiting_title)
    await message.answer(
        "🎨 <b>Create Action Message</b>\n\n"
        "<b>Step 1 / 3</b> — Enter the <b>title</b> (shown in bold):\n\n"
        "<i>Example: 🎉 Big announcement!</i>",
        reply_markup=cancel_kb()
    )


@router.message(ActionMsgState.waiting_title)
async def action_title_received(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.update_data(title=message.text.strip())
    await state.set_state(ActionMsgState.waiting_body)
    await message.answer(
        "<b>Step 2 / 3</b> — Enter the <b>body text</b>:\n\n"
        "<i>HTML tags supported: &lt;b&gt;, &lt;i&gt;, &lt;code&gt;</i>",
        reply_markup=cancel_kb()
    )


@router.message(ActionMsgState.waiting_body)
async def action_body_received(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.update_data(body=message.text.strip())
    await state.set_state(ActionMsgState.waiting_buttons)
    await message.answer(
        "<b>Step 3 / 3</b> — Enter <b>action buttons</b>, one per line:\n\n"
        "Format: <code>Button label | callback_or_url</code>\n\n"
        "Callback examples:\n"
        "<code>⚡ Pul ishlash 💰 | action:earn</code>\n"
        "<code>💰 Ovoz berish 📦 | action:vote</code>\n"
        "<code>🎁 Sovgani olish 🎁 | action:reward</code>\n\n"
        "URL example (starts with http):\n"
        "<code>🌐 Open website 🔗 | https://example.com</code>\n\n"
        "<i>Each line → one wide button + ↗ arrow (like the screenshot).</i>",
        reply_markup=cancel_kb()
    )


@router.message(ActionMsgState.waiting_buttons)
async def action_buttons_received(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id): return
    raw = message.text.strip()
    buttons, errors = [], []

    for i, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if "|" not in line:
            errors.append(f"Line {i}: missing '|' separator")
            continue
        label, target = [p.strip() for p in line.split("|", 1)]
        if not label or not target:
            errors.append(f"Line {i}: empty label or target")
            continue
        buttons.append((label, target))

    if errors:
        await message.answer(
            "❌ <b>Fix these errors:</b>\n\n" + "\n".join(f"• {e}" for e in errors),
            reply_markup=cancel_kb()
        )
        return
    if not buttons:
        await message.answer("❌ No valid buttons found.", reply_markup=cancel_kb())
        return

    data = await state.get_data()
    await state.update_data(buttons=buttons)
    await state.set_state(ActionMsgState.confirm)

    preview = _build_action_text(data["title"], data["body"])
    await message.answer("👀 <b>Preview:</b>\n\n" + preview,
                         reply_markup=action_buttons_kb(buttons))
    await message.answer("Send to:", reply_markup=_send_options_kb())


@router.callback_query(F.data.startswith("actionsend:"))
async def action_send(call: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(call.from_user.id): return
    target = call.data.split(":", 1)[1]
    data = await state.get_data()
    await state.clear()

    text    = _build_action_text(data.get("title", ""), data.get("body", ""))
    buttons = data.get("buttons", [])
    kb      = action_buttons_kb(buttons)

    if target == "me":
        await bot.send_message(call.from_user.id, text, reply_markup=kb)
        await call.message.edit_text("✅ Sent to you as preview.")
    else:
        users = await get_all_users()
        total = len(users)
        sent = failed = 0
        await call.message.edit_text(f"📢 Sending action message to {total} users...")
        for i, uid in enumerate(users):
            try:
                await bot.send_message(uid, text, reply_markup=kb)
                sent += 1
            except Exception:
                failed += 1
            if (i + 1) % 25 == 0:
                await asyncio.sleep(1)
        await call.message.edit_text(
            f"✅ <b>Done!</b>  Sent: {sent}  Failed: {failed}"
        )
    await call.answer()


# ─── /test_friday — manual trigger ────────────────────────────

@router.message(Command("test_friday"))
async def test_friday(message: Message, bot: Bot):
    if not is_admin(message.from_user.id): return
    await message.answer("🏆 Running Friday reward manually...")
    from utils.scheduler import _give_friday_rewards
    await _give_friday_rewards(bot)
    await message.answer("✅ Friday reward complete!")


# ─── USER ACTION CALLBACKS ────────────────────────────────────

@router.callback_query(F.data.startswith("action:"))
async def handle_action_callback(call: CallbackQuery):
    action = call.data.split(":", 1)[1]
    RESPONSES = {
        "earn":   "💰 <b>Earn Money</b>\n\nThis feature is coming soon! Stay tuned.",
        "vote":   "📦 <b>Vote</b>\n\nYour vote has been registered! Thank you.",
        "reward": "🎁 <b>Claim Reward</b>\n\nYour reward is being processed!",
    }
    text = RESPONSES.get(action, f"✅ Action <b>{action}</b> registered!")
    await call.answer(text[:200], show_alert=True)
