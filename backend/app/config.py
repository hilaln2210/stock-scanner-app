from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database
    database_url: str = "sqlite+aiosqlite:///./stocks.db"

    # Scraping
    scrape_interval_minutes: int = 10
    max_news_age_hours: int = 48

    # Finviz Elite (optional)
    finviz_email: str = ""
    finviz_password: str = ""
    finviz_cookie: str = ""
    finviz_api_token: str = ""

    # AI Assistant
    anthropic_api_key: str = ""

    # Gemini AI (Smart Portfolio Brain)
    gemini_api_key: str = ""

    # Groq AI (Primary Brain — ultra-fast Llama inference)
    groq_api_key: str = ""

    # Telegram Alerts
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Email (Daily Summary)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    email_to: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000


settings = Settings()
