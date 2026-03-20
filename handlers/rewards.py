"""
Rewards & Gamification Admin Panel
- Configure quiz rewards (passes per N correct)
- Configure streak rewards
- Give bulk rewards to all/top users
- View reward history
"""
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import settings
from database.users import get_all_users, get_leaderboard, add_free_pass, update_user, grant_vip, revoke_vip
from keyboards.admin import back_admin_kb
from keyboards.user import cancel_kb
import asyncio

router = Router()


def is_admin(uid): return uid in settings.admin_id_list


def rewards_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎫 Give Pass to ALL",       callback_data="rwd:all_pass")],
        [InlineKeyboardButton(text="🏆 Reward Top 3 Inviters",  callback_data="rwd:top3")],
        [InlineKeyboardButton(text="👑 VIP to Top Inviter",     callback_data="rwd:vip_top")],
        [InlineKeyboardButton(text="📢 Announce Reward",        callback_data="rwd:announce")],
        [InlineKeyboardButton(text="◀️ Back",                   callback_data="adm:main")],
    ])


@router.callback_query(F.data == "adm:rewards")
async def adm_rewards(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text(
        "🎁 <b>Rewards Panel</b>\n\n"
        "Manually trigger rewards or run special campaigns:",
        reply_markup=rewards_kb()
    )
    await call.answer()


@router.callback_query(F.data == "rwd:all_pass")
async def rwd_all_pass(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.update_data(rwd_action="all_pass")
    await call.message.edit_text(
        "🎫 <b>Give Free Pass to ALL users</b>\n\n"
        "How many passes to give each user?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="1 pass",  callback_data="rwd_amt:1"),
             InlineKeyboardButton(text="2 passes", callback_data="rwd_amt:2")],
            [InlineKeyboardButton(text="3 passes", callback_data="rwd_amt:3"),
             InlineKeyboardButton(text="5 passes", callback_data="rwd_amt:5")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="adm:rewards")],
        ])
    )
    await call.answer()


@router.callback_query(F.data == "rwd:top3")
async def rwd_top3(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id): return
    top = await get_leaderboard(3)
    if not top:
        await call.answer("No users yet.", show_alert=True)
        return
    prizes  = [5, 3, 1]
    medals  = ["🥇", "🥈", "🥉"]
    report  = "🏆 <b>Top 3 Reward Sent!</b>\n\n"
    for i, u in enumerate(top):
        passes = prizes[i]
        await add_free_pass(u["tg_id"], passes)
        name = u.get("full_name") or "User"
        report += f"{medals[i]} <b>{name}</b> — +{passes} 🎫\n"
        try:
            await bot.send_message(
                u["tg_id"],
                f"{medals[i]} <b>Congratulations!</b>\n\n"
                f"You're in the <b>Top {i+1}</b> on the invite leaderboard!\n"
                f"🎫 You received <b>{passes} Free Pass{'es' if passes > 1 else ''}</b>!"
            )
        except Exception:
            pass
    await call.message.edit_text(report, reply_markup=back_admin_kb("rewards"))
    await call.answer()


@router.callback_query(F.data == "rwd:vip_top")
async def rwd_vip_top(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id): return
    top = await get_leaderboard(1)
    if not top:
        await call.answer("No users yet.", show_alert=True)
        return
    u = top[0]
    # VIP expires after 10 VIP lessons unlocked
    await grant_vip(u["tg_id"], lesson_limit=10, granted_by=call.from_user.id, reason="top_inviter_reward")
    name = u.get("full_name") or "User"
    try:
        await bot.send_message(
            u["tg_id"],
            f"👑 <b>You've been granted VIP!</b>\n\n"
            f"🏆 As the top inviter you get VIP access!\n"
            f"🎓 Lesson allowance: <b>10 VIP lessons</b>\n\n"
            f"Keep inviting friends to earn more! 💪"
        )
    except Exception:
        pass
    await call.message.edit_text(
        f"✅ <b>VIP (10 lessons) granted to {name}!</b>",
        reply_markup=back_admin_kb("rewards")
    )
    await call.answer()


class AnnounceState(StatesGroup):
    waiting_text = State()


@router.callback_query(F.data == "rwd:announce")
async def rwd_announce(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(AnnounceState.waiting_text)
    await call.message.edit_text(
        "📢 <b>Reward Announcement</b>\n\n"
        "Send the announcement message.\n"
        "HTML formatting supported.",
        reply_markup=cancel_kb()
    )
    await call.answer()


@router.message(AnnounceState.waiting_text)
async def rwd_announce_send(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id): return
    await state.clear()
    users = await get_all_users()
    sent = failed = 0
    status = await message.answer(f"📢 Sending to {len(users)} users...")
    for i, uid in enumerate(users):
        try:
            await bot.send_message(uid, message.text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
        if (i + 1) % 25 == 0:
            await asyncio.sleep(1)
    await status.edit_text(
        f"✅ <b>Announcement sent!</b>\n✅ {sent}  ❌ {failed}"
    )


@router.callback_query(F.data.startswith("rwd_amt:"))
async def rwd_give_amount(call: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(call.from_user.id): return
    amount = int(call.data.split(":")[1])
    await state.clear()
    users = await get_all_users()
    sent = failed = 0
    await call.message.edit_text(f"🎫 Giving {amount} pass(es) to {len(users)} users...")
    for i, uid in enumerate(users):
        try:
            await add_free_pass(uid, amount)
            await bot.send_message(
                uid,
                f"🎁 <b>Free Gift!</b>\n\n"
                f"🎫 You received <b>{amount} Free Pass{'es' if amount > 1 else ''}</b> from the admin!\n"
                f"Use them to unlock lessons. 🎓"
            )
            sent += 1
        except Exception:
            failed += 1
        if (i + 1) % 25 == 0:
            await asyncio.sleep(1)
    await call.message.edit_text(
        f"✅ <b>Done!</b>\n🎫 {amount} pass(es) given to {sent} users.",
        reply_markup=back_admin_kb("rewards")
    )
    await call.answer()
