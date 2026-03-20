import logging
from typing import Callable, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from database.users import get_or_create_user

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, (Message, CallbackQuery)):
            tg_user = event.from_user
            if tg_user:
                try:
                    user = await get_or_create_user(
                        tg_id=tg_user.id,
                        username=tg_user.username,
                        full_name=tg_user.full_name,
                    )
                    if user and user.get("is_banned"):
                        if isinstance(event, Message):
                            await event.answer("🚫 You are banned.")
                        elif isinstance(event, CallbackQuery):
                            await event.answer("🚫 You are banned.", show_alert=True)
                        return
                except Exception as e:
                    logger.error(f"AuthMiddleware error: {e}")

        data["db_user"] = user
        return await handler(event, data)
