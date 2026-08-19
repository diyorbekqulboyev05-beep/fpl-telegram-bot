from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from bot.config.settings import get_settings

class Base(DeclarativeBase): pass

settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def init_db():
    import os
    os.makedirs('data', exist_ok=True)
    from bot.database import models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
