# FPL Telegram Bot

Python 3.11+, `python-telegram-bot`, APScheduler va FPL public API asosidagi modul bot. Asia/Tashkent timezone’da FPL statistikasi asosida o‘zbekcha HTML postlar tayyorlaydi va kanalga yuboradi.

## Ishga tushirish
1. Python 3.11+ o‘rnating.
2. `python -m venv .venv` va aktivatsiya qiling.
3. `pip install -r requirements.txt`.
4. BotFather’da bot yarating va token oling.
5. Botni kanalga administrator qilib, post yuborish huquqini bering.
6. `.env.example` nusxasini `.env` qiling; `BOT_TOKEN`, `CHANNEL_ID`, `ADMIN_IDS` ni to‘ldiring. `CHANNEL_ID` username (`@kanal`) yoki numeric ID bo‘lishi mumkin.
7. `python main.py` bilan ishga tushiring.

`ADMIN_IDS` — buyruqlarni ishlata oladigan Telegram user ID’larining vergul bilan ajratilgan ro‘yxati. OpenAI ixtiyoriy: kalit bo‘lmasa template fallback ishlaydi. FPL API vaqtincha ishlamasa client oxirgi cache’ni qaytaradi va job keyingi vazifaga davom etadi.

## Docker/VPS
`cp .env.example .env`, qiymatlarni kiriting, so‘ng `docker compose up -d --build` bajaring. `restart: unless-stopped` server reboot’dan keyin avtomatik qayta ishga tushiradi. SQLite `fpl_data` volume’da saqlanadi; PostgreSQL uchun `DATABASE_URL=postgresql+asyncpg://...` kiriting.

## Buyruqlar
`/start`, `/status`, `/post matn`, `/schedule`, `/on`, `/off`, `/captain`, `/players`, `/settings`.

Production kengaytmalari: RSS feed adapterini ko‘paytirish, PostgreSQL migration, live event hash snapshotlari va OpenAI adapterini `post_generator.py` ichida ulash. FPL official endpointlari o‘zgarsa, faqat `fpl_client.py` adapteri yangilanadi; scraping o‘rniga qonuniy provider/API ishlating.
