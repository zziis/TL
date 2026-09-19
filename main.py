import asyncio
import logging
import uvicorn
from config import HOST, PORT, BOT_TOKEN, ADMIN_SECRET_KEY, WEBAPP_URL
from server import app
from bot import start_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("ShabahLauncher")

async def run_fastapi_server():
    config = uvicorn.Config(
        app=app,
        host=HOST,
        port=PORT,
        log_level="info",
        access_log=False
    )
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    print("""
    ========================================================
       💀 مــنــصــة شــبــح | SHABAH NEON PLATFORM 💀
    ========================================================
    ⚡ النظام نشط ومشفر بالكامل
    🌐 رابط المنصة (Telegram Mini App): http://localhost:{port}
    🛡️ رابط لوحة المطور: http://localhost:{port}/ghost-admin?secret={secret}
    📡 حالة بوت تلجرام: {bot_status}
    ========================================================
    """.format(
        port=PORT,
        secret=ADMIN_SECRET_KEY,
        bot_status="متصل وشغال ✅" if BOT_TOKEN else "غير مفعل (في انتظار وضع BOT_TOKEN في .env) ⚠️"
    ))

    # Run both the FastAPI server and Telegram Bot concurrently
    tasks = [
        asyncio.create_task(run_fastapi_server())
    ]
    
    if BOT_TOKEN:
        tasks.append(asyncio.create_task(start_bot()))
    else:
        logger.warning("BOT_TOKEN is empty. Run with web server only. Set BOT_TOKEN in .env to enable Telegram Bot.")

    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("💀 تم إيقاف منصة شبح.")
