from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from bot.config.settings import get_settings
from bot.services.extras import (deadline_watch, gw_summary_watch, guarded, injury_watch,
                                 pre_deadline_watch, price_watch)
from bot.services.live_matches import live_watch


def setup_scheduler(app):
    s = get_settings()
    scheduler = AsyncIOScheduler(timezone=s.timezone)
    every_refresh = IntervalTrigger(minutes=s.fpl_refresh_minutes)
    jobs = [
        ('deadline_watch', deadline_watch, every_refresh),
        ('pre_deadline_watch', pre_deadline_watch, every_refresh),
        ('price_watch', price_watch, every_refresh),
        ('injury_watch', injury_watch, every_refresh),
        ('gw_summary_watch', gw_summary_watch, every_refresh),
        ('live_watch', live_watch, IntervalTrigger(minutes=1)),
    ]
    for name, fn, trigger in jobs:
        scheduler.add_job(guarded(name, fn), trigger, args=[app], id=name,
                          replace_existing=True, next_run_time=datetime.now())
    scheduler.start()
    return scheduler
