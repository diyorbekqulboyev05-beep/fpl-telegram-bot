from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    bot_token: str
    channel_id: str
    admin_ids: str = ''
    database_url: str = 'sqlite+aiosqlite:///./data/fpl_bot.db'
    openai_api_key: str | None = None
    openai_model: str = 'gpt-4o-mini'
    timezone: str = 'Asia/Tashkent'
    auto_posts_enabled: bool = True
    deadline_hours: int = 3
    fpl_refresh_minutes: int = 15
    live_poll_minutes: int = 5
    news_feeds: str = ''
    daily_news_time: str = '09:00'
    daily_player_watch_time: str = '18:00'

    @property
    def admins(self) -> set[int]:
        return {int(x.strip()) for x in self.admin_ids.split(',') if x.strip()}
    @property
    def feeds(self) -> list[str]:
        return [x.strip() for x in self.news_feeds.split(',') if x.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings()
