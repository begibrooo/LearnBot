"""
Weekly Friday reward scheduler.
Every Friday at 18:00 (UTC) the top 3 inviters receive free passes:
  🥇 1st place → 5 free passes
  🥈 2nd place → 3 free passes
  🥉 3rd place → 1 free pass

Also sends an announcement to ALL users showing the winners.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from aiogram import Bot
from database.users import get_leaderboard, add_free_pass, get_all_users

logger = logging.getLogger(__name__)

FRIDAY = 4          # weekday(): Monday=0 … Friday=4
REWARD_HOUR = 18    # UTC hour to fire
REWARD_MINUTE = 0

PRIZES = [5, 3, 1]  # passes for 1st, 2nd, 3rd
MEDALS = ["🥇", "🥈", "🥉"]


async def _seconds_until_next_friday() -> float:
    now = datetime.now(timezone.utc)
    days_ahead = (FRIDAY - now.weekday()) % 7
    if days_ahead == 0 and (now.hour > REWARD_HOUR or
                             (now.hour == REWARD_HOUR and now.minute >= REWARD_MINUTE)):
        days_ahead = 7  # already passed this Friday → next week
    target = now.replace(hour=REWARD_HOUR, minute=REWARD_MINUTE, second=0, microsecond=0)
    target += timedelta(days=days_ahead)
    return (target - now).total_seconds()


async def _give_friday_rewards(bot: Bot):
    """Core reward logic — give passes to top 3 and announce."""
    top = await get_leaderboard(3)
    if not top:
        logger.info("Friday reward: no users in leaderboard.")
        return

    winners_text = ""
    for i, user in enumerate(top):
        passes = PRIZES[i] if i < len(PRIZES) else 1
        medal  = MEDALS[i]
        name   = user.get("full_name") or "Anonymous"
        uid    = user["tg_id"]
        invites = user.get("invites_count", 0)

        await add_free_pass(uid, passes)
        winners_text += f"{medal} <b>{name}</b> — {invites} invites → +{passes} 🎫\n"

        try:
            await bot.send_message(
                uid,
                f"🏆 <b>Friday Reward!</b>\n\n"
                f"You ranked <b>{medal}</b> on this week's invite leaderboard!\n\n"
                f"🎫 You received <b>{passes} Free Pass{'es' if passes > 1 else ''}</b>!\n\n"
                f"Keep inviting friends to win more next Friday! 💪"
            )
        except Exception as e:
            logger.warning(f"Could not notify winner {uid}: {e}")

    # Broadcast announcement to all users
    announcement = (
        f"🏆 <b>Weekly Leaderboard Winners!</b>\n\n"
        f"Congratulations to this week's top inviters:\n\n"
        f"{winners_text}\n"
        f"👥 Invite more friends to win <b>Free Passes</b> next Friday!\n"
        f"Use /start to get your invite link."
    )
    all_users = await get_all_users()
    sent = 0
    for uid in all_users:
        try:
            await bot.send_message(uid, announcement)
            sent += 1
        except Exception:
            pass
        if sent % 25 == 0:
            await asyncio.sleep(1)

    logger.info(f"Friday rewards given. Winners: {len(top)}. Broadcast: {sent}/{len(all_users)}")


async def friday_reward_loop(bot: Bot):
    """Run forever. Sleeps until next Friday, fires rewards, sleeps again."""
    while True:
        wait = await _seconds_until_next_friday()
        h, m = divmod(int(wait) // 60, 60)
        logger.info(f"Next Friday reward in {h}h {m}m")
        await asyncio.sleep(wait)
        try:
            await _give_friday_rewards(bot)
        except Exception as e:
            logger.error(f"Friday reward error: {e}")
        await asyncio.sleep(60)   # prevent double-fire
