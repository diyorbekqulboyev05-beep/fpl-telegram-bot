from datetime import datetime, timezone as dt_timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from bot.config.settings import get_settings
from bot.database.models import JobRun
from bot.database.session import Session
from bot.services.analytics import current_event
from bot.services.post_generator import deadline_post
from bot.services.live_matches import live_watch


async def deadline_watch(app):
    """Checks every fpl_refresh_minutes whether the current gameweek's
    deadline falls within deadline_hours from now, and posts a reminder
    once (deduplicated via JobRun) if so."""
    s = get_settings()
    if not s.auto_posts_enabled:
        return
    try:
        data = await app.bot_data['fpl'].bootstrap()
        event = current_event(data)
        if not event or not event.get('deadline_time'):
            return
        deadline = datetime.fromisoformat(event['deadline_time'].replace('Z', '+00:00'))
        now = datetime.now(dt_timezone.utc)
        hours_left = (deadline - now).total_seconds() / 3600
        if not (0 <= hours_left <= s.deadline_hours):
            return
        key = f"deadline_reminder_gw{event.get('id')}"
        async with Session() as db:
            exists = (await db.execute(select(JobRun).where(JobRun.key == key))).scalar_one_or_none()
            if exists:
                return
            await app.bot_data['publisher'].send(deadline_post(data), 'deadline', force=True)
            db.add(JobRun(key=key))
            await db.commit()
    except Exception:
        app.bot_data['logger'].exception('deadline watch failed')


def setup_scheduler(app):
    s = get_settings()
    scheduler = AsyncIOScheduler(timezone=s.timezone)
    scheduler.add_job(deadline_watch, IntervalTrigger(minutes=s.fpl_refresh_minutes), args=[app],
                       id='deadline_watch', replace_existing=True, next_run_time=datetime.now())
    scheduler.add_job(live_watch, IntervalTrigger(minutes=1), args=[app],
                       id='live_watch', replace_existing=True, next_run_time=datetime.now())
    scheduler.start()
    return scheduler
