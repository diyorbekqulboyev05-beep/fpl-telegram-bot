import asyncio, logging
import httpx

log = logging.getLogger(__name__)
BASE = 'https://fantasy.premierleague.com/api'

class FPLClient:
    def __init__(self):
        self.client = httpx.AsyncClient(base_url=BASE, timeout=20, headers={'User-Agent':'FPL-Telegram-Bot/1.0'})
        self.cache: dict[str, object] = {}
    async def get(self, path: str):
        for attempt in range(3):
            try:
                r = await self.client.get(path); r.raise_for_status(); data = r.json(); self.cache[path] = data; return data
            except Exception as exc:
                log.warning('FPL request failed %s: %s', path, exc)
                if attempt < 2: await asyncio.sleep(2 ** attempt)
        return self.cache.get(path, {})
    async def bootstrap(self): return await self.get('/bootstrap-static/')
    async def fixtures(self): return await self.get('/fixtures/')
    async def live(self, gw: int): return await self.get(f'/event/{gw}/live/')
    async def close(self): await self.client.aclose()
