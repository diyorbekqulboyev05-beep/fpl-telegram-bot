from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from bot.database.session import Base

class BotSetting(Base):
    __tablename__ = 'settings'
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)

class PublishedPost(Base):
    __tablename__ = 'published_posts'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    post_type: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class SeenNews(Base):
    __tablename__ = 'seen_news'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    news_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class JobRun(Base):
    __tablename__ = 'job_runs'
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LiveMatchMessage(Base):
    __tablename__ = 'live_match_messages'
    match_date: Mapped[str] = mapped_column(String(10), primary_key=True)  # YYYY-MM-DD, bot timezone
    chat_id: Mapped[str] = mapped_column(String(64))
    message_id: Mapped[int] = mapped_column(Integer)
    last_content_hash: Mapped[str] = mapped_column(String(64), default='')
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
