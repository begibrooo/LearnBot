from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_IDS: str = ""
    CONTENT_CHANNEL_ID: str = ""
    REQUIRED_CHANNELS: str = ""
    INVITES_PER_FREE_PASS: int = 5
    THROTTLE_RATE: float = 0.5
    MAX_WRONG_ATTEMPTS: int = 3
    LOCKOUT_MINUTES: int = 15

    # ── AI Chat ───────────────────────────────────────────────
    AI_PROVIDER: str = "groq"
    AI_API_KEY: str = ""
    AI_MODEL: str = ""
    AI_SYSTEM_PROMPT: str = (
        "You are a helpful learning assistant for LearnBot educational platform. "
        "Help students understand lessons, answer questions clearly and concisely, "
        "encourage them to keep learning. Be friendly, motivating and educational."
    )
    AI_MAX_HISTORY: int = 20
    AI_MAX_TOKENS: int = 1024
    AI_DAILY_LIMIT: int = 50

    # ── Web App ───────────────────────────────────────────────
    WEBAPP_URL: str = ""       # e.g. https://your-app.netlify.app
    WEBAPP_PORT: int = 8080    # API server port

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def admin_id_list(self) -> list[int]:
        if not self.ADMIN_IDS:
            return []
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()]

    @property
    def required_channel_list(self) -> list[str]:
        if not self.REQUIRED_CHANNELS:
            return []
        return [x.strip() for x in self.REQUIRED_CHANNELS.split(",") if x.strip()]

    @property
    def ai_model_name(self) -> str:
        if self.AI_MODEL:
            return self.AI_MODEL
        return {
            "openai":    "gpt-4o-mini",
            "anthropic": "claude-3-5-haiku-20241022",
            "groq":      "llama-3.3-70b-versatile",
        }.get(self.AI_PROVIDER, "llama-3.3-70b-versatile")


settings = Settings()
