import time
import logging
from typing import Callable, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from config import settings

logger = logging.getLogger(__name__)
_rate_cache: dict[int, float] = {}


class ThrottleMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.from_user:
            uid = event.from_user.id
            now = time.monotonic()
            last = _rate_cache.get(uid, 0)
            if now - last < settings.THROTTLE_RATE:
                return
            _rate_cache[uid] = now
        return await handler(event, data)
