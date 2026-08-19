from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from bot.config.settings import get_settings
from bot.services.post_generator import captain_post, deadline_post, players_post

settings=get_settings()
def admin_only(fn):
    async def wrapped(update, context):
        if update.effective_user and update.effective_user.id in settings.admins: return await fn(update,context)
        await update.effective_message.reply_text('Ruxsat yo‘q.')
    return wrapped

@admin_only
async def start(update, context): await update.message.reply_text('FPL bot tayyor. /status, /post, /schedule, /on, /off, /captain, /players, /settings')
@admin_only
async def status(update, context): await update.message.reply_text(f'Bot: faol\nAuto posts: {settings.auto_posts_enabled}\nTimezone: {settings.timezone}')
@admin_only
async def schedule(update, context): await update.message.reply_text('09:00 — FPL News\n18:00 — Player Watch\nDeadline — 3 soat oldin\nGW yakuni — avtomatik')
@admin_only
async def toggle(update, context):
    settings.auto_posts_enabled = update.message.text.strip() == '/on'; await update.message.reply_text(f'Auto posts: {settings.auto_posts_enabled}')
@admin_only
async def captain(update, context): await update.message.reply_text(captain_post(await context.bot_data['fpl'].bootstrap()), parse_mode='HTML')
@admin_only
async def players(update, context): await update.message.reply_text(players_post(await context.bot_data['fpl'].bootstrap()), parse_mode='HTML')
@admin_only
async def post(update, context):
    text=' '.join(context.args) or 'Post matni berilmagan.'; await context.bot_data['publisher'].send(text, 'manual', force=True); await update.message.reply_text('Kanalga yuborildi.')
@admin_only
async def settings_cmd(update, context): await update.message.reply_text(f'CHANNEL_ID: {settings.channel_id}\nDeadline offset: {settings.deadline_hours} soat\nRefresh: {settings.fpl_refresh_minutes} daqiqa')
def handlers():
    return [CommandHandler('start',start),CommandHandler('status',status),CommandHandler('schedule',schedule),CommandHandler('on',toggle),CommandHandler('off',toggle),CommandHandler('captain',captain),CommandHandler('players',players),CommandHandler('post',post),CommandHandler('settings',settings_cmd)]
