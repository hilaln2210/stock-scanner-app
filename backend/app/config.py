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

    # AI Assistant
    anthropic_api_key: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000


settings = Settings()
