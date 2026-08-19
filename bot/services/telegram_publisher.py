from sqlalchemy import select
from bot.database.models import PublishedPost
from bot.database.session import Session
from bot.services.post_generator import post_hash

class Publisher:
    def __init__(self, bot, channel_id): self.bot=bot; self.channel_id=channel_id
    async def send(self, text, post_type='manual', force=False):
        digest=post_hash(text)
        async with Session() as db:
            exists=(await db.execute(select(PublishedPost).where(PublishedPost.content_hash==digest))).scalar_one_or_none()
            if exists and not force: return False
            await self.bot.send_message(chat_id=self.channel_id, text=text, parse_mode='HTML', disable_web_page_preview=True)
            db.add(PublishedPost(content_hash=digest, post_type=post_type)); await db.commit(); return True
