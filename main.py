import logging
from telegram.ext import Application
from bot.config.settings import get_settings
from bot.database.session import init_db
from bot.handlers.admin import handlers
from bot.services.fpl_client import FPLClient
from bot.services.telegram_publisher import Publisher
from bot.schedulers.setup import setup_scheduler

async def post_init(app):
    await init_db(); app.bot_data['fpl']=FPLClient(); app.bot_data['publisher']=Publisher(app.bot, get_settings().channel_id); app.bot_data['logger']=logging.getLogger('jobs'); setup_scheduler(app)
async def post_shutdown(app): await app.bot_data['fpl'].close()
def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    s=get_settings(); app=Application.builder().token(s.bot_token).post_init(post_init).post_shutdown(post_shutdown).build()
    for handler in handlers(): app.add_handler(handler)
    app.run_polling(allowed_updates=['message'])
if __name__=='__main__': main()
