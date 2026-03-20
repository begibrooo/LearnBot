import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

from config import settings
from database.db import init_db, migrate_db
from middlewares.auth import AuthMiddleware
from middlewares.throttle import ThrottleMiddleware
from handlers import (
    start, menu, lessons, profile, search,
    promo, referral, leaderboard, support,
    admin_main, admin_content, admin_promo,
    admin_users, admin_broadcast, subscription,
    actions, checkin, quiz, notes, stats,
    rewards, reminders, feedback,
    admin_members, achievements, daily_challenge,
    ai_chat, admin_games
)
from utils.scheduler import friday_reward_loop
from handlers.reminders import reminder_loop
from webapp_api import create_webapp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Starting LearnBot...")
    await init_db()
    await migrate_db()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(ThrottleMiddleware())
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    for router in [
        start.router, subscription.router, menu.router, lessons.router,
        profile.router, search.router, promo.router, referral.router,
        leaderboard.router, support.router, admin_main.router,
        admin_content.router, admin_promo.router, admin_users.router,
        admin_broadcast.router, actions.router, checkin.router, quiz.router,
        notes.router, stats.router, rewards.router, reminders.router,
        feedback.router, admin_members.router, achievements.router,
        daily_challenge.router, ai_chat.router, admin_games.router,
    ]:
        dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(friday_reward_loop(bot))
    asyncio.create_task(reminder_loop(bot))

    # Railway provides PORT automatically — use it
    port = int(os.environ.get("PORT", 8080))
    webapp = create_webapp()
    runner = web.AppRunner(webapp)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Web server on port {port} — Railway URL is your webapp URL")

    logger.info("Bot polling started.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
