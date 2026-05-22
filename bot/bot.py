import os
import asyncio
import logging
import tempfile
import re
import json
import uuid
from pathlib import Path

import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

SUPPORTED_DOMAINS = [
    "youtube.com", "youtu.be",
    "instagram.com",
    "tiktok.com", "vm.tiktok.com",
]

URL_PATTERN = re.compile(r"https?://[^\s]+")
MAX_FILE_SIZE_MB = 50
USER_DATA_FILE = "bot/user_data.json"

STRINGS = {
    "en": {
        "start": (
            "👋 Hello! I'm a video downloader bot.\n\n"
            "Send me a video link from:\n"
            "• YouTube\n"
            "• Instagram\n"
            "• TikTok\n\n"
            "I'll download and send it back to you!\n\n"
            "Use /language to change language."
        ),
        "choose_language": "🌐 Choose your language:",
        "language_set": "✅ Language set to English.",
        "choose_format": "🎞 Choose format:",
        "choose_quality": "📺 Choose quality:",
        "downloading": "⏳ Downloading, please wait...",
        "sending": "📤 Sending...",
        "done": "✅ Done!",
        "too_large": f"❌ File exceeds {MAX_FILE_SIZE_MB}MB limit. Try a shorter video or lower quality.",
        "download_error": "❌ Could not download. The link may be private, expired, or unsupported.",
        "generic_error": "❌ Something went wrong. Please try again.",
        "unsupported": "⚠️ Unsupported platform. Please send a YouTube, Instagram, or TikTok link.",
        "no_url": "Please send a valid video URL from YouTube, Instagram, or TikTok.",
        "fmt_video": "🎬 Video (MP4)",
        "fmt_mp3": "🎵 MP3 (audio)",
        "fmt_voice": "🎙 Voice message",
        "q_360": "360p",
        "q_720": "720p",
        "q_1080": "1080p",
        "q_best": "⭐ Best quality",
        "cancelled": "❌ Cancelled.",
    },
    "ru": {
        "start": (
            "👋 Привет! Я бот для скачивания видео.\n\n"
            "Отправь мне ссылку с:\n"
            "• YouTube\n"
            "• Instagram\n"
            "• TikTok\n\n"
            "Я скачаю и пришлю тебе видео!\n\n"
            "Используй /language для смены языка."
        ),
        "choose_language": "🌐 Выберите язык:",
        "language_set": "✅ Язык изменён на Русский.",
        "choose_format": "🎞 Выберите формат:",
        "choose_quality": "📺 Выберите качество:",
        "downloading": "⏳ Скачиваю, подождите...",
        "sending": "📤 Отправляю...",
        "done": "✅ Готово!",
        "too_large": f"❌ Файл превышает {MAX_FILE_SIZE_MB}МБ. Попробуйте более короткое видео или меньшее качество.",
        "download_error": "❌ Не удалось скачать. Ссылка может быть приватной, устаревшей или неподдерживаемой.",
        "generic_error": "❌ Что-то пошло не так. Попробуйте ещё раз.",
        "unsupported": "⚠️ Неподдерживаемая платформа. Отправьте ссылку с YouTube, Instagram или TikTok.",
        "no_url": "Отправьте корректную ссылку с YouTube, Instagram или TikTok.",
        "fmt_video": "🎬 Видео (MP4)",
        "fmt_mp3": "🎵 MP3 (аудио)",
        "fmt_voice": "🎙 Голосовое сообщение",
        "q_360": "360p",
        "q_720": "720p",
        "q_1080": "1080p",
        "q_best": "⭐ Лучшее качество",
        "cancelled": "❌ Отменено.",
    },
    "uz": {
        "start": (
            "👋 Salom! Men video yuklovchi botman.\n\n"
            "Menga quyidagi saytlardan havola yuboring:\n"
            "• YouTube\n"
            "• Instagram\n"
            "• TikTok\n\n"
            "Men videoni yuklab, sizga yuboraman!\n\n"
            "Tilni o'zgartirish uchun /language buyrug'ini ishlating."
        ),
        "choose_language": "🌐 Tilni tanlang:",
        "language_set": "✅ Til O'zbek tiliga o'zgartirildi.",
        "choose_format": "🎞 Formatni tanlang:",
        "choose_quality": "📺 Sifatni tanlang:",
        "downloading": "⏳ Yuklanmoqda, iltimos kuting...",
        "sending": "📤 Yuborilmoqda...",
        "done": "✅ Tayyor!",
        "too_large": f"❌ Fayl {MAX_FILE_SIZE_MB}MB dan katta. Qisqaroq video yoki past sifatni sinab ko'ring.",
        "download_error": "❌ Yuklab bo'lmadi. Havola shaxsiy, muddati o'tgan yoki qo'llab-quvvatlanmasligi mumkin.",
        "generic_error": "❌ Xato yuz berdi. Iltimos qaytadan urinib ko'ring.",
        "unsupported": "⚠️ Qo'llab-quvvatlanmaydigan platforma. YouTube, Instagram yoki TikTok havolasini yuboring.",
        "no_url": "YouTube, Instagram yoki TikTok dan to'g'ri video havolasini yuboring.",
        "fmt_video": "🎬 Video (MP4)",
        "fmt_mp3": "🎵 MP3 (audio)",
        "fmt_voice": "🎙 Ovozli xabar",
        "q_360": "360p",
        "q_720": "720p",
        "q_1080": "1080p",
        "q_best": "⭐ Eng yaxshi sifat",
        "cancelled": "❌ Bekor qilindi.",
    },
}

LANG_DETECT_MAP = {
    "ru": "ru",
    "uz": "uz",
    "uk": "ru",
}

pending_downloads: dict[str, dict] = {}


def load_user_data() -> dict:
    if Path(USER_DATA_FILE).exists():
        with open(USER_DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_user_data(data: dict) -> None:
    Path(USER_DATA_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(USER_DATA_FILE, "w") as f:
        json.dump(data, f)


def get_user_lang(user_id: int, telegram_lang: str | None = None) -> str:
    data = load_user_data()
    uid = str(user_id)
    if uid in data:
        return data[uid].get("lang", "en")
    if telegram_lang:
        base = telegram_lang.split("-")[0].lower()
        return LANG_DETECT_MAP.get(base, "en")
    return "en"


def set_user_lang(user_id: int, lang: str) -> None:
    data = load_user_data()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {}
    data[uid]["lang"] = lang
    save_user_data(data)


def t(user_id: int, key: str, telegram_lang: str | None = None) -> str:
    lang = get_user_lang(user_id, telegram_lang)
    return STRINGS.get(lang, STRINGS["en"]).get(key, STRINGS["en"].get(key, key))


def is_supported_url(url: str) -> bool:
    return any(domain in url for domain in SUPPORTED_DOMAINS)


def format_keyboard(user_id: int, dl_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(user_id, "fmt_video"), callback_data=f"fmt:video:{dl_id}"),
            InlineKeyboardButton(t(user_id, "fmt_mp3"), callback_data=f"fmt:mp3:{dl_id}"),
        ],
        [
            InlineKeyboardButton(t(user_id, "fmt_voice"), callback_data=f"fmt:voice:{dl_id}"),
        ],
    ])


def quality_keyboard(user_id: int, dl_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(user_id, "q_360"), callback_data=f"q:360:{dl_id}"),
            InlineKeyboardButton(t(user_id, "q_720"), callback_data=f"q:720:{dl_id}"),
        ],
        [
            InlineKeyboardButton(t(user_id, "q_1080"), callback_data=f"q:1080:{dl_id}"),
            InlineKeyboardButton(t(user_id, "q_best"), callback_data=f"q:best:{dl_id}"),
        ],
    ])


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"),
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang:ru"),
            InlineKeyboardButton("🇺🇿 O'zbek", callback_data="lang:uz"),
        ]
    ])


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    lang = user.language_code if user else None
    await update.message.reply_text(t(user.id, "start", lang))


async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    lang = user.language_code if user else None
    await update.message.reply_text(
        t(user.id, "choose_language", lang),
        reply_markup=language_keyboard(),
    )


async def handle_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user = query.from_user
    lang = query.data.split(":")[1]
    set_user_lang(user.id, lang)
    await query.edit_message_text(t(user.id, "language_set"))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = update.message.text or ""
    urls = URL_PATTERN.findall(text)

    if not urls:
        await update.message.reply_text(t(user.id, "no_url", user.language_code))
        return

    url = urls[0]

    if not is_supported_url(url):
        await update.message.reply_text(t(user.id, "unsupported", user.language_code))
        return

    dl_id = uuid.uuid4().hex[:12]
    pending_downloads[dl_id] = {"url": url, "user_id": user.id}

    await update.message.reply_text(
        t(user.id, "choose_format", user.language_code),
        reply_markup=format_keyboard(user.id, dl_id),
    )


async def handle_format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user = query.from_user
    _, fmt, dl_id = query.data.split(":", 2)

    if dl_id not in pending_downloads:
        await query.edit_message_text(t(user.id, "cancelled"))
        return

    pending_downloads[dl_id]["fmt"] = fmt

    if fmt == "video":
        await query.edit_message_text(
            t(user.id, "choose_quality"),
            reply_markup=quality_keyboard(user.id, dl_id),
        )
    else:
        await query.edit_message_text(t(user.id, "downloading"))
        await process_download(query, user, dl_id, quality="best")


async def handle_quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user = query.from_user
    _, quality, dl_id = query.data.split(":", 2)

    if dl_id not in pending_downloads:
        await query.edit_message_text(t(user.id, "cancelled"))
        return

    await query.edit_message_text(t(user.id, "downloading"))
    await process_download(query, user, dl_id, quality=quality)


async def process_download(query, user, dl_id: str, quality: str) -> None:
    entry = pending_downloads.pop(dl_id, None)
    if not entry:
        await query.edit_message_text(t(user.id, "cancelled"))
        return

    url = entry["url"]
    fmt = entry.get("fmt", "video")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = await download_file(url, tmpdir, fmt, quality)

            if filepath is None or not Path(filepath).exists():
                await query.edit_message_text(t(user.id, "download_error"))
                return

            file_size = Path(filepath).stat().st_size
            if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
                await query.edit_message_text(t(user.id, "too_large"))
                return

            await query.edit_message_text(t(user.id, "sending"))

            with open(filepath, "rb") as f:
                if fmt == "mp3":
                    await query.message.reply_audio(
                        audio=f,
                        read_timeout=120,
                        write_timeout=120,
                    )
                elif fmt == "voice":
                    await query.message.reply_voice(
                        voice=f,
                        read_timeout=120,
                        write_timeout=120,
                    )
                else:
                    await query.message.reply_video(
                        video=f,
                        supports_streaming=True,
                        read_timeout=120,
                        write_timeout=120,
                    )

            await query.edit_message_text(t(user.id, "done"))

    except yt_dlp.utils.DownloadError as e:
        logger.error("Download error: %s", e)
        await query.edit_message_text(t(user.id, "download_error"))
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        await query.edit_message_text(t(user.id, "generic_error"))


def build_ydl_opts(output_dir: str, fmt: str, quality: str) -> dict:
    base = {
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }

    if fmt == "mp3":
        base.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
    elif fmt == "voice":
        base.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "vorbis",
            }],
            "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        })
    else:
        height_map = {"360": 360, "720": 720, "1080": 1080}
        if quality in height_map:
            h = height_map[quality]
            fmt_str = (
                f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]"
                f"/bestvideo[height<={h}]+bestaudio"
                f"/best[height<={h}]"
                f"/best"
            )
        else:
            fmt_str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

        base.update({
            "format": fmt_str,
            "merge_output_format": "mp4",
        })

    return base


async def download_file(url: str, output_dir: str, fmt: str, quality: str) -> str | None:
    ydl_opts = build_ydl_opts(output_dir, fmt, quality)
    loop = asyncio.get_event_loop()

    def _download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                return None
            filename = ydl.prepare_filename(info)
            path = Path(filename)

            if fmt == "mp3":
                mp3 = path.with_suffix(".mp3")
                if mp3.exists():
                    return str(mp3)
            elif fmt == "voice":
                for ext in [".ogg", ".opus"]:
                    p = path.with_suffix(ext)
                    if p.exists():
                        return str(p)

            if path.exists():
                return str(path)

            mp4 = path.with_suffix(".mp4")
            if mp4.exists():
                return str(mp4)

            files = list(Path(output_dir).glob("*"))
            return str(files[0]) if files else None

    return await loop.run_in_executor(None, _download)


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("language", cmd_language))
    app.add_handler(CallbackQueryHandler(handle_language_callback, pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(handle_format_callback, pattern=r"^fmt:"))
    app.add_handler(CallbackQueryHandler(handle_quality_callback, pattern=r"^q:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
