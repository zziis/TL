import asyncio
import logging
from typing import Optional
from pathlib import Path
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, FSInputFile
from config import BOT_TOKEN, DEVELOPER_ID, WEBAPP_URL, ADMIN_SECRET_KEY, ADMIN_IDS
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


def is_admin(user_id) -> bool:
    uid = str(user_id)
    return uid == str(DEVELOPER_ID) or uid in {str(x) for x in ADMIN_IDS}


def get_start_keyboard(admin: bool = False):
    is_https = WEBAPP_URL.startswith("https://")
    buttons = []

    if admin and is_https:
        admin_url = f"{WEBAPP_URL}/ghost-admin?secret={ADMIN_SECRET_KEY}"
        buttons.append([
            InlineKeyboardButton(text="👥 فتح قائمة المستخدمين ", url=admin_url)
        ])
    elif is_https:
        buttons.append([
            InlineKeyboardButton(
                text="⚡ دخول منصة  ",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )
        ])
    elif WEBAPP_URL:
        buttons.append([
            InlineKeyboardButton(text="⚡ فتح منصة ZLZ", url=WEBAPP_URL)
        ])

    buttons.append([
        InlineKeyboardButton(text="📡 مفعل ✅", callback_data="server_status")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


if dp:
    @dp.message(CommandStart())
    async def start_handler(message: types.Message):
        user = message.from_user
        user_id = str(user.id)

        if await db.is_banned(user_id):
            await message.answer("🚫 تم حظرك من الوصول إلى المنصة بقرار من الإدارة.")
            return

        admin = is_admin(user.id)
        if admin:
            caption = (
                "⚡ <b>لوحة ZLZ | زلزال</b> ⚡\n\n"
                "👑 أهلاً بالمطور.\n"
                "💬 الرسائل والاتصالات الخاصة تظهر لك مباشرة.\n"
                "🔐 دخول إداري مشفّر وآمن."
            )
        else:
            caption = (
                "✨ <b>مرحباً بك في بوت | زلزال</b> ✨\n\n"
                "⚡ <b>منطقة التواصل المباشر</b>\n"
                "💬  رسالتك تصل مباشرة من البوت\n"
                 "💬او من داخل المنصة\n"
                "📞 اتصال صوتي أو مرئي بعد الموافقة\n\n"
                "💠 <b>ZLZ — حضور مختلف</b> 💠"
            )

        animation_path = Path(__file__).resolve().parent / "static" / "assets" / "zlz_welcome_neon_fast.gif"
        try:
            await message.answer_animation(
                animation=FSInputFile(animation_path),
                caption=caption,
                reply_markup=get_start_keyboard(admin),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Welcome animation failed: {e}")
            await message.answer(caption, reply_markup=get_start_keyboard(admin), parse_mode="HTML")

        if not admin:
            asyncio.create_task(notify_admin_new_visitor(user))

    @dp.callback_query(F.data == "server_status")
    async def callback_status(call: types.CallbackQuery):
        await call.answer("⚡ منصة زلزال نشطة والاتصال مشفر وجاهز!", show_alert=True)


# Direct Telegram relay: user <-> developer
_admin_message_to_user = {}
_activated_users = set()

if dp:
    @dp.message(F.chat.type == "private", ~F.text.startswith("/"))
    async def relay_user_to_developer(message: types.Message):
        if not DEVELOPER_ID or is_admin(message.from_user.id):
            # Developer/admin replies to a relayed message
            if is_admin(message.from_user.id) and message.reply_to_message:
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
                await message.answer("✓ تم فتح اتصالك المباشر مع زلزال، يمكنك الآن الإرسال والاستلام مباشرة.")
        except Exception as e:
            logger.error(f"User relay failed: {e}")


async def notify_admin_new_visitor(user: types.User):
    if not bot or not DEVELOPER_ID:
        return
    try:
        text = (
            f"🚨 <b>زائر جديد دخل بوت زلزال!</b>\n\n"
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



async def notify_admin_web_message(user_name: str, user_id: str, content: str = "", msg_type: str = "text"):
    """Notify developer in Telegram when a private Mini App message arrives."""
    if not bot or not DEVELOPER_ID or not WEBAPP_URL:
        return
    try:
        labels = {
            "text": "💬 رسالة",
            "voice": "🎙️ بصمة صوتية",
            "image": "📷 صورة",
            "file": "📎 ملف"
        }
        label = labels.get(msg_type, "💬 رسالة")
        preview = (content or "").strip()[:180]

        text = (
            f"{label} <b>جديدة من منصة ZLZ</b>\n"
            f"👤 <b>{user_name}</b>\n"
            f"🆔 <code>{user_id}</code>"
        )
        if preview:
            text += f"\n\n{preview}"

        admin_url = f"{WEBAPP_URL}/ghost-admin?secret={ADMIN_SECRET_KEY}"
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="👤 فتح محادثة المستخدم", url=admin_url)
        ]])

        admin_targets = ADMIN_IDS if ADMIN_IDS else [DEVELOPER_ID]
        for admin_id in admin_targets:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            except Exception as send_error:
                logger.error(f"Failed to notify admin {admin_id}: {send_error}")
    except Exception as e:
        logger.error(f"Failed to notify admin about web message: {e}")


async def notify_admin_call_request(user_name: str, user_id: str, call_type: str, call_id: str):
    """Notify developer via Telegram that someone requested a voice/video call"""
    if not bot or not DEVELOPER_ID:
        return
    try:
        icon = "🎙️ مايك (صوت)" if call_type == "voice" else "📷 كاميرا وفيديو"
        text = (
            f"📞 <b>طلب اتصال جديد في منصة زلزال!</b>\n\n"
            f"👤 <b>المستخدم:</b> {user_name} (<code>{user_id}</code>)\n"
            f"📡 <b>النوع:</b> {icon}\n"
            f"🆔 <b>رقم المكالمة:</b> <code>{call_id}</code>\n\n"
            f"⚡ ادخل لوحة المطور لقبول المكالمة أو الرفض."
        )
        admin_url = f"{WEBAPP_URL}/ghost-admin?secret={ADMIN_SECRET_KEY}"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡ فتح لوحة تحكم زلزال", url=admin_url)]
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
