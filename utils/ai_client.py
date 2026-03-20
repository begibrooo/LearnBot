"""
AI Client — Groq (primary) with OpenAI/Anthropic fallback support.
Set AI_PROVIDER=groq and AI_API_KEY=your_groq_key in .env
Get free key at: https://console.groq.com
"""
import logging
import aiohttp
from config import settings

logger = logging.getLogger(__name__)

GROQ_BASE    = "https://api.groq.com/openai/v1"
OPENAI_BASE  = "https://api.openai.com/v1"


async def ask_ai(messages: list[dict]) -> str:
    """
    Send messages to configured AI provider.
    messages = [{"role": "system"|"user"|"assistant", "content": "..."}]
    Returns the assistant reply string.
    """
    provider = settings.AI_PROVIDER.lower()
    key      = settings.AI_API_KEY
    model    = settings.ai_model_name

    if not key:
        return (
            "⚠️ AI chat is not configured yet.\n\n"
            "Admin needs to add <b>AI_API_KEY</b> to environment variables.\n"
            "Get a free Groq key at: https://console.groq.com"
        )

    try:
        if provider == "anthropic":
            return await _ask_anthropic(messages, model, key)
        else:
            base = GROQ_BASE if provider == "groq" else OPENAI_BASE
            return await _ask_openai_compat(messages, model, key, base)
    except Exception as e:
        logger.error(f"AI error ({provider}/{model}): {e}")
        err = str(e)
        if "rate_limit" in err.lower():
            return "⏳ AI is busy right now. Try again in a moment."
        if "invalid_api_key" in err.lower() or "401" in err:
            return "❌ Invalid AI API key. Contact admin."
        return f"⚠️ AI temporarily unavailable. Try again later."


async def _ask_openai_compat(messages: list, model: str, key: str, base_url: str) -> str:
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":       model,
        "messages":    messages,
        "max_tokens":  settings.AI_MAX_TOKENS,
        "temperature": 0.7,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            data = await resp.json()
            if "error" in data:
                raise ValueError(data["error"].get("message", str(data["error"])))
            return data["choices"][0]["message"]["content"].strip()


async def _ask_anthropic(messages: list, model: str, key: str) -> str:
    system = next((m["content"] for m in messages if m["role"] == "system"), settings.AI_SYSTEM_PROMPT)
    msgs   = [m for m in messages if m["role"] != "system"]
    headers = {
        "x-api-key":         key,
        "anthropic-version": "2023-06-01",
        "Content-Type":      "application/json",
    }
    payload = {
        "model":      model,
        "max_tokens": settings.AI_MAX_TOKENS,
        "system":     system,
        "messages":   msgs,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            data = await resp.json()
            if "error" in data:
                raise ValueError(data["error"].get("message", str(data["error"])))
            return data["content"][0]["text"].strip()
