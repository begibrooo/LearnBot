"""
Safe channel info fetcher.
bot.get_chat() crashes on channels with paid/custom reactions (aiogram 3.7 pydantic bug).
We bypass this by calling the raw Telegram HTTP API directly and parsing only what we need.
"""
import logging
import aiohttp

logger = logging.getLogger(__name__)


async def safe_get_chat(bot, chat_id: str) -> dict | None:
    """
    Returns a plain dict with: id, title, username, type
    Never raises on unknown reaction types or future Telegram fields.
    """
    token = bot.token
    url = f"https://api.telegram.org/bot{token}/getChat"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"chat_id": chat_id}) as resp:
                data = await resp.json()
        if not data.get("ok"):
            raise ValueError(data.get("description", "Unknown error"))
        result = data["result"]
        return {
            "id":       result["id"],
            "title":    result.get("title", ""),
            "username": result.get("username"),   # may be None for private channels
            "type":     result.get("type", "channel"),
        }
    except Exception as e:
        logger.error(f"safe_get_chat({chat_id}): {e}")
        raise


async def safe_get_chat_member(bot, chat_id: str, user_id: int) -> str:
    """
    Returns member status string or 'left' on any error.
    Also never crashes on unknown reaction types.
    """
    token = bot.token
    url = f"https://api.telegram.org/bot{token}/getChatMember"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"chat_id": chat_id, "user_id": user_id}) as resp:
                data = await resp.json()
        if not data.get("ok"):
            return "left"
        return data["result"].get("status", "left")
    except Exception as e:
        logger.warning(f"safe_get_chat_member({chat_id}, {user_id}): {e}")
        return "left"
