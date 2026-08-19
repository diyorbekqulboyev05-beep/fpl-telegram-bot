from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from bot.config.settings import get_settings
from bot.services.post_generator import captain_post, players_post

async def publish(app, factory, kind):
    s=get_settings()
    if not s.auto_posts_enabled: return
    try: await app.bot_data['publisher'].send(factory(await app.bot_data['fpl'].bootstrap()), kind)
    except Exception: app.bot_data['logger'].exception('scheduled job failed: %s', kind)

def setup_scheduler(app):
    s=get_settings(); scheduler=AsyncIOScheduler(timezone=s.timezone)
    h,m=map(int,s.daily_news_time.split(':')); scheduler.add_job(publish,'cron',hour=h,minute=m,args=[app,players_post,'daily_news'],id='daily_news',replace_existing=True)
    h,m=map(int,s.daily_player_watch_time.split(':')); scheduler.add_job(publish,'cron',hour=h,minute=m,args=[app,captain_post,'captain'],id='captain',replace_existing=True)
    scheduler.start(); return scheduler
