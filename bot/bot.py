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
COOKIES_FILE = "bot/cookies.txt"
MAX_RETRIES = 3

TIKTOK_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/16.0 Mobile/15E148 Safari/604.1"
)

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
        "downloading_retry": "⏳ Retrying download (attempt {attempt}/{max})...",
        "sending": "📤 Sending...",
        "done": "✅ Done!",
        "too_large": f"❌ File exceeds {MAX_FILE_SIZE_MB}MB limit. Try a shorter video or lower quality.",
        "download_error": "❌ Could not download. The link may be private, expired, or unsupported.",
        "error_private": "🔒 This content is private or requires login. Only public videos can be downloaded.",
        "error_geo": "🌍 This video is not available in the current region (geo-restricted).",
        "error_removed": "🚫 This video has been removed or is no longer available.",
        "error_youtube": "❌ YouTube download failed. The video may be age-restricted or unavailable.",
        "error_instagram": "❌ Instagram download failed. Only public posts can be downloaded.",
        "error_tiktok": "❌ TikTok download failed. The video may have been removed or restricted.",
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
        "downloading_retry": "⏳ Повторная попытка ({attempt}/{max})...",
        "sending": "📤 Отправляю...",
        "done": "✅ Готово!",
        "too_large": f"❌ Файл превышает {MAX_FILE_SIZE_MB}МБ. Попробуйте более короткое видео или меньшее качество.",
        "download_error": "❌ Не удалось скачать. Ссылка может быть приватной, устаревшей или неподдерживаемой.",
        "error_private": "🔒 Этот контент приватный или требует авторизации. Можно скачивать только публичные видео.",
        "error_geo": "🌍 Это видео недоступно в данном регионе (географическое ограничение).",
        "error_removed": "🚫 Это видео было удалено или больше не доступно.",
        "error_youtube": "❌ Ошибка загрузки YouTube. Видео может быть с возрастным ограничением или недоступно.",
        "error_instagram": "❌ Ошибка загрузки Instagram. Можно скачивать только публичные публикации.",
        "error_tiktok": "❌ Ошибка загрузки TikTok. Видео может быть удалено или ограничено.",
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
        "downloading_retry": "⏳ Qayta urinish ({attempt}/{max})...",
        "sending": "📤 Yuborilmoqda...",
        "done": "✅ Tayyor!",
        "too_large": f"❌ Fayl {MAX_FILE_SIZE_MB}MB dan katta. Qisqaroq video yoki past sifatni sinab ko'ring.",
        "download_error": "❌ Yuklab bo'lmadi. Havola shaxsiy, muddati o'tgan yoki qo'llab-quvvatlanmasligi mumkin.",
        "error_private": "🔒 Bu kontent shaxsiy yoki kirish talab qiladi. Faqat ochiq videolarni yuklab olish mumkin.",
        "error_geo": "🌍 Bu video hozirgi mintaqada mavjud emas (geo-cheklov).",
        "error_removed": "🚫 Bu video o'chirilgan yoki endi mavjud emas.",
        "error_youtube": "❌ YouTube yuklab olish muvaffaqiyatsiz. Video yosh cheklovi yoki mavjud emaslik tufayli bo'lishi mumkin.",
        "error_instagram": "❌ Instagram yuklab olish muvaffaqiyatsiz. Faqat ochiq postlarni yuklab olish mumkin.",
        "error_tiktok": "❌ TikTok yuklab olish muvaffaqiyatsiz. Video o'chirilgan yoki cheklangan bo'lishi mumkin.",
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


def t(user_id: int, key: str, telegram_lang: str | None = None, **kwargs) -> str:
    lang = get_user_lang(user_id, telegram_lang)
    text = STRINGS.get(lang, STRINGS["en"]).get(key, STRINGS["en"].get(key, key))
    return text.format(**kwargs) if kwargs else text


def is_supported_url(url: str) -> bool:
    return any(domain in url for domain in SUPPORTED_DOMAINS)


def detect_platform(url: str) -> str:
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    if "instagram.com" in url:
        return "instagram"
    if "tiktok.com" in url:
        return "tiktok"
    return "unknown"


def classify_error(error_msg: str, platform: str) -> str:
    msg = error_msg.lower()
    if any(k in msg for k in ("private", "login", "sign in", "authentication", "requires auth")):
        return "error_private"
    if any(k in msg for k in ("geo", "not available in your country", "region")):
        return "error_geo"
    if any(k in msg for k in ("removed", "no longer available", "deleted", "does not exist", "404")):
        return "error_removed"
    platform_map = {"youtube": "error_youtube", "instagram": "error_instagram", "tiktok": "error_tiktok"}
    return platform_map.get(platform, "download_error")


def build_ydl_opts(output_dir: str, fmt: str, quality: str, platform: str) -> dict:
    cookies_file = COOKIES_FILE if Path(COOKIES_FILE).exists() else None

    base: dict = {
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "retries": 1,
        "socket_timeout": 30,
    }

    if cookies_file:
        base["cookiefile"] = cookies_file
        logger.info("Using cookies file: %s", cookies_file)

    if platform == "youtube":
        base.update({
            "extractor_args": {"youtube": {"skip": ["dash", "hls"]}},
        })
    elif platform == "tiktok":
        base.update({
            "http_headers": {"User-Agent": TIKTOK_USER_AGENT},
        })
    elif platform == "instagram":
        base.update({
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        })

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
        })
    else:
        height_map = {"360": 360, "720": 720, "1080": 1080}
        max_size = f"[filesize<{MAX_FILE_SIZE_MB}M]"

        if quality in height_map:
            h = height_map[quality]
            if platform == "youtube":
                fmt_str = (
                    f"best[height<={h}]{max_size}"
                    f"/best[height<={h}]"
                    f"/best{max_size}"
                    f"/best"
                )
            else:
                fmt_str = (
                    f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]"
                    f"/bestvideo[height<={h}]+bestaudio"
                    f"/best[height<={h}]"
                    f"/best"
                )
        else:
            if platform == "youtube":
                fmt_str = f"best{max_size}/best"
            else:
                fmt_str = (
                    f"bestvideo[ext=mp4]+bestaudio[ext=m4a]"
                    f"/bestvideo+bestaudio"
                    f"/best"
                )

        base.update({
            "format": fmt_str,
            "merge_output_format": "mp4",
        })

    return base


def _find_output_file(output_dir: str, prepared_path: str, fmt: str) -> str | None:
    path = Path(prepared_path)

    if fmt == "mp3":
        for candidate in [path.with_suffix(".mp3"), *Path(output_dir).glob("*.mp3")]:
            if candidate.exists():
                return str(candidate)
    elif fmt == "voice":
        for ext in [".ogg", ".opus", ".webm"]:
            candidate = path.with_suffix(ext)
            if candidate.exists():
                return str(candidate)
        for ext in ["*.ogg", "*.opus", "*.webm"]:
            matches = list(Path(output_dir).glob(ext))
            if matches:
                return str(matches[0])
    else:
        for candidate in [path, path.with_suffix(".mp4")]:
            if candidate.exists():
                return str(candidate)

    files = [f for f in Path(output_dir).iterdir() if f.is_file()]
    return str(files[0]) if files else None


async def download_file(
    url: str, output_dir: str, fmt: str, quality: str, platform: str
) -> tuple[str | None, str | None]:
    last_error: str | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        ydl_opts = build_ydl_opts(output_dir, fmt, quality, platform)
        loop = asyncio.get_event_loop()

        def _download(opts=ydl_opts):
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    return None
                return ydl.prepare_filename(info)

        try:
            prepared_path = await loop.run_in_executor(None, _download)
            if prepared_path is None:
                last_error = "no_info"
                continue

            filepath = _find_output_file(output_dir, prepared_path, fmt)
            if filepath:
                return filepath, None

            last_error = "file_not_found"

        except yt_dlp.utils.DownloadError as e:
            raw = str(e)
            logger.warning("Attempt %d/%d failed for %s: %s", attempt, MAX_RETRIES, platform, raw)
            last_error = raw
            error_key = classify_error(raw, platform)
            if error_key in ("error_private", "error_removed", "error_geo"):
                return None, error_key
        except Exception as e:
            logger.error("Unexpected error on attempt %d: %s", attempt, e)
            last_error = str(e)

        if attempt < MAX_RETRIES:
            await asyncio.sleep(2 * attempt)

    error_key = classify_error(last_error or "", platform) if last_error else "download_error"
    return None, error_key


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
    platform = detect_platform(url)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            for attempt in range(1, MAX_RETRIES + 1):
                if attempt > 1:
                    try:
                        await query.edit_message_text(
                            t(user.id, "downloading_retry", attempt=attempt, max=MAX_RETRIES)
                        )
                    except Exception:
                        pass
                    await asyncio.sleep(2 * (attempt - 1))

                filepath, error_key = await download_file(url, tmpdir, fmt, quality, platform)

                if filepath is not None:
                    break

                if error_key in ("error_private", "error_removed", "error_geo"):
                    await query.edit_message_text(t(user.id, error_key))
                    return

                if attempt == MAX_RETRIES:
                    await query.edit_message_text(t(user.id, error_key or "download_error"))
                    return

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

    except Exception as e:
        logger.error("Unexpected error in process_download: %s", e)
        await query.edit_message_text(t(user.id, "generic_error"))


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
