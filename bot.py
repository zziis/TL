import asyncio
import logging
from typing import Optional
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from config import BOT_TOKEN, DEVELOPER_ID, WEBAPP_URL, ADMIN_SECRET_KEY
from database import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ShabahBot")

bot: Optional[Bot] = None
dp: Optional[Dispatcher] = None

if BOT_TOKEN:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
else:
    logger.warning("⚠️ BOT_TOKEN is not set. Bot will run in mock/standby mode.")


def get_start_keyboard():
    # If URL is https, we can use web_app button. If localhost or http, URL button is used.
    is_https = WEBAPP_URL.startswith("https://")
    
    buttons = []
    if is_https:
        buttons.append([
            InlineKeyboardButton(
                text="💀 دخول منصة شبح (Mini App) ⚡",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )
        ])
    else:
        buttons.append([
            InlineKeyboardButton(
                text="💀 فتح منصة شبح في المتصفح ⚡",
                url=WEBAPP_URL
            )
        ])
        
    buttons.append([
        InlineKeyboardButton(
            text="📡 حالة السيرفر: متصل ✅",
            callback_data="server_status"
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


if dp:
    @dp.message(CommandStart())
    async def start_handler(message: types.Message):
        user = message.from_user
        user_id = str(user.id)
        
        # Check ban status
        if await db.is_banned(user_id):
            await message.answer("🚫 تم حظرك من الوصول إلى منصة شبح بقرار من الإدارة.")
            return

        welcome_text = (
            "✦ <b>مرحباً بك في خَيال</b> ✦\n\n"
            "مساحة خاصة للتواصل المباشر مع المطور.\n\n"
            "💬 رسائلك تصل للمطور مباشرة\n"
            "🎙️ أرسل رسالة أو بصمة صوتية\n"
            "📷 أرسل الصور والملفات\n"
            "📞 اتصال صوتي أو مرئي عند الموافقة\n\n"
            "<b>اكتب رسالتك مباشرة أو افتح المنصة من الزر أدناه.</b>"
        )
        
        await message.answer(
            welcome_text,
            reply_markup=get_start_keyboard(),
            parse_mode="HTML"
        )
        
        # Notify developer about new visitor
        await notify_admin_new_visitor(user)

    @dp.callback_query(F.data == "server_status")
    async def callback_status(call: types.CallbackQuery):
        await call.answer("⚡ منصة شبح نشطة والاتصال مشفر وجاهز!", show_alert=True)


# Direct Telegram relay: user <-> developer
_admin_message_to_user = {}
_activated_users = set()

if dp:
    @dp.message(F.chat.type == "private", ~F.text.startswith("/"))
    async def relay_user_to_developer(message: types.Message):
        if not DEVELOPER_ID or str(message.from_user.id) == str(DEVELOPER_ID):
            # Developer replies to a relayed message
            if str(message.from_user.id) == str(DEVELOPER_ID) and message.reply_to_message:
                target = _admin_message_to_user.get(message.reply_to_message.message_id)
                if target:
                    try:
                        await bot.copy_message(chat_id=target, from_chat_id=message.chat.id, message_id=message.message_id)
                    except Exception as e:
                        logger.error(f"Developer relay failed: {e}")
            return
        uid = str(message.from_user.id)
        try:
            header = await bot.send_message(
                chat_id=DEVELOPER_ID,
                text=f"💬 <b>رسالة من مستخدم</b>\n👤 {message.from_user.full_name}\n🆔 <code>{uid}</code>",
                parse_mode="HTML"
            )
            copied = await bot.copy_message(chat_id=DEVELOPER_ID, from_chat_id=message.chat.id, message_id=message.message_id)
            _admin_message_to_user[header.message_id] = message.from_user.id
            _admin_message_to_user[copied.message_id] = message.from_user.id
            if uid not in _activated_users:
                _activated_users.add(uid)
                await message.answer("✓ تم فتح اتصالك المباشر مع المطور، يمكنك الآن الإرسال والاستلام مباشرة.")
        except Exception as e:
            logger.error(f"User relay failed: {e}")


async def notify_admin_new_visitor(user: types.User):
    if not bot or not DEVELOPER_ID:
        return
    try:
        text = (
            f"🚨 <b>زائر جديد دخل بوت شبح!</b>\n\n"
            f"👤 <b>الاسم:</b> {user.full_name}\n"
            f"🆔 <b>الآيدي:</b> <code>{user.id}</code>\n"
            f"🔗 <b>اليوزر:</b> @{user.username if user.username else 'بدون'}\n"
            f"🕒 <b>الوقت:</b> الآن"
        )
        await bot.send_message(
            chat_id=DEVELOPER_ID,
            text=text,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify admin about visitor: {e}")


async def notify_admin_call_request(user_name: str, user_id: str, call_type: str, call_id: str):
    """Notify developer via Telegram that someone requested a voice/video call"""
    if not bot or not DEVELOPER_ID:
        return
    try:
        icon = "🎙️ مايك (صوت)" if call_type == "voice" else "📷 كاميرا وفيديو"
        text = (
            f"📞 <b>طلب اتصال جديد في منصة شبح!</b>\n\n"
            f"👤 <b>المستخدم:</b> {user_name} (<code>{user_id}</code>)\n"
            f"📡 <b>النوع:</b> {icon}\n"
            f"🆔 <b>رقم المكالمة:</b> <code>{call_id}</code>\n\n"
            f"⚡ ادخل لوحة المطور لقبول المكالمة أو الرفض."
        )
        admin_url = f"{WEBAPP_URL}/ghost-admin?secret={ADMIN_SECRET_KEY}"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡ فتح لوحة تحكم شبح", url=admin_url)]
        ])
        await bot.send_message(
            chat_id=DEVELOPER_ID,
            text=text,
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify admin about call: {e}")


async def start_bot():
    if bot and dp:
        logger.info("🚀 Starting Shabah Telegram Bot Polling...")
        try:
            await dp.start_polling(bot)
        except Exception as e:
            logger.error(f"Telegram Bot error: {e}")
    else:
        logger.info("ℹ️ Telegram bot not configured. Running without bot polling.")
