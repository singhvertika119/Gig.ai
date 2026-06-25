from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Gig.ai API"
    debug: bool = False
    mongodb_uri: str = "mongodb://mongodb:27017"
    mongodb_db: str = "gigai"
    database_url: str = "sqlite+aiosqlite:///gigai.db"
    gemini_model: str = "gemini-2.5-flash"
    gemini_api_key: str | None = None
    google_api_key: str | None = None
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    n8n_webhook_url: str = "http://n8n:5678/webhook-test/invoice-reminder"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    discord_webhook_url: str | None = None


settings = Settings()
