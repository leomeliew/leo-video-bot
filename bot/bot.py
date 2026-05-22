import os
import asyncio
import logging
import tempfile
import re
import json
import uuid
from pathlib import Path

import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
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

# Load cookies from environment variable if available
import base64
_cookies_env = os.environ.get("INSTAGRAM_COOKIES")
if _cookies_env:
    try:
        with open(COOKIES_FILE, "wb") as _f:
            _f.write(base64.b64decode(_cookies_env))
    except Exception:
        pass
        _youtube_cookies = os.environ.get("YOUTUBE_COOKIES")

if _youtube_cookies:
    try:
        with open("youtube_cookies.txt", "w") as f:
            f.write(_youtube_cookies)
    except Exception:
        pass
MAX_RETRIES = 3

CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

TIKTOK_USER_AGENT = "TikTok 26.2.0 rv:262018 (iPhone; iOS 14.4.2; en_US) Cronet"

STRINGS = {
    "en": {
        "start": (
            "👋 Hello! I'm a video downloader bot.\n\n"
            "Send me a link from:\n"
            "• YouTube\n"
            "• Instagram (photos, videos, reels, stories, carousels)\n"
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
        "error_private": "🔒 This content is private. Only public posts can be downloaded.",
        "error_geo": "🌍 This video is not available in the current region (geo-restricted).",
        "error_removed": "🚫 This content has been removed or is no longer available.",
        "error_youtube": "❌ YouTube download failed. The video may be age-restricted or unavailable.",
        "error_instagram": "❌ Instagram download failed. Only public posts can be downloaded.",
        "error_tiktok": "❌ TikTok download failed. The video may have been removed or restricted.",
        "generic_error": "❌ Something went wrong. Please try again.",
        "unsupported": "⚠️ Unsupported platform. Please send a YouTube, Instagram, or TikTok link.",
        "no_url": "Please send a valid URL from YouTube, Instagram, or TikTok.",
        "fmt_video": "🎬 Video (MP4)",
        "fmt_mp3": "🎵 MP3 (audio)",
        "fmt_voice": "🎙 Voice message",
        "q_360": "360p",
        "q_720": "720p",
        "q_1080": "1080p",
        "q_best": "⭐ Best quality",
        "cancelled": "❌ Cancelled.",
        "ig_detecting": "🔍 Detecting content type...",
        "ig_photo": "📷 Downloading photo...",
        "ig_carousel": "🖼 Downloading album ({count} photos)...",
        "ig_sending_photo": "📤 Sending photo...",
        "ig_sending_album": "📤 Sending album...",
        "ig_story": "📖 Downloading story...",
        "ig_reel": "🎬 Downloading reel...",
    },
    "ru": {
        "start": (
            "👋 Привет! Я бот для скачивания контента.\n\n"
            "Отправь мне ссылку с:\n"
            "• YouTube\n"
            "• Instagram (фото, видео, рилсы, истории, карусели)\n"
            "• TikTok\n\n"
            "Я скачаю и пришлю тебе!\n\n"
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
        "error_private": "🔒 Этот контент приватный. Можно скачивать только публичные публикации.",
        "error_geo": "🌍 Это видео недоступно в данном регионе (географическое ограничение).",
        "error_removed": "🚫 Этот контент был удалён или больше не доступен.",
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
        "ig_detecting": "🔍 Определяю тип контента...",
        "ig_photo": "📷 Скачиваю фото...",
        "ig_carousel": "🖼 Скачиваю альбом ({count} фото)...",
        "ig_sending_photo": "📤 Отправляю фото...",
        "ig_sending_album": "📤 Отправляю альбом...",
        "ig_story": "📖 Скачиваю историю...",
        "ig_reel": "🎬 Скачиваю рилс...",
    },
    "uz": {
        "start": (
            "👋 Salom! Men kontent yuklovchi botman.\n\n"
            "Menga quyidagi saytlardan havola yuboring:\n"
            "• YouTube\n"
            "• Instagram (rasmlar, videolar, reelslar, hikoyalar, karusellar)\n"
            "• TikTok\n\n"
            "Men yuklab, sizga yuboraman!\n\n"
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
        "error_private": "🔒 Bu kontent shaxsiy. Faqat ochiq postlarni yuklab olish mumkin.",
        "error_geo": "🌍 Bu video hozirgi mintaqada mavjud emas (geo-cheklov).",
        "error_removed": "🚫 Bu kontent o'chirilgan yoki endi mavjud emas.",
        "error_youtube": "❌ YouTube yuklab olish muvaffaqiyatsiz. Video yosh cheklovi yoki mavjud emaslik tufayli bo'lishi mumkin.",
        "error_instagram": "❌ Instagram yuklab olish muvaffaqiyatsiz. Faqat ochiq postlarni yuklab olish mumkin.",
        "error_tiktok": "❌ TikTok yuklab olish muvaffaqiyatsiz. Video o'chirilgan yoki cheklangan bo'lishi mumkin.",
        "generic_error": "❌ Xato yuz berdi. Iltimos qaytadan urinib ko'ring.",
        "unsupported": "⚠️ Qo'llab-quvvatlanmaydigan platforma. YouTube, Instagram yoki TikTok havolasini yuboring.",
        "no_url": "YouTube, Instagram yoki TikTok dan to'g'ri havolasini yuboring.",
        "fmt_video": "🎬 Video (MP4)",
        "fmt_mp3": "🎵 MP3 (audio)",
        "fmt_voice": "🎙 Ovozli xabar",
        "q_360": "360p",
        "q_720": "720p",
        "q_1080": "1080p",
        "q_best": "⭐ Eng yaxshi sifat",
        "cancelled": "❌ Bekor qilindi.",
        "ig_detecting": "🔍 Kontent turini aniqlanmoqda...",
        "ig_photo": "📷 Rasm yuklanmoqda...",
        "ig_carousel": "🖼 Albom yuklanmoqda ({count} rasm)...",
        "ig_sending_photo": "📤 Rasm yuborilmoqda...",
        "ig_sending_album": "📤 Albom yuborilmoqda...",
        "ig_story": "📖 Hikoya yuklanmoqda...",
        "ig_reel": "🎬 Reels yuklanmoqda...",
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
        if platform == "youtube":
            return "download_error"
        return "error_private"
    if any(k in msg for k in ("geo", "not available in your country", "region")):
        return "error_geo"
    if any(k in msg for k in ("removed", "no longer available", "deleted", "does not exist", "404")):
        return "error_removed"
    platform_map = {"youtube": "error_youtube", "instagram": "error_instagram", "tiktok": "error_tiktok"}
    return platform_map.get(platform, "download_error")


def _ig_base_opts() -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "http_headers": {"User-Agent": TIKTOK_USER_AGENT},
    }
    if Path(COOKIES_FILE).exists():
        opts["cookiefile"] = COOKIES_FILE
    return opts


def _entry_is_photo(entry: dict) -> bool:
    vcodec = entry.get("vcodec", "")
    ext = entry.get("ext", "")
    return vcodec in ("none", "") or ext in ("jpg", "jpeg", "webp", "png")


async def detect_instagram_type(url: str) -> dict:
    """
    Returns dict with:
      - type: 'photo' | 'carousel' | 'video' | 'reel' | 'story'
      - entries: list of info dicts (for carousel, one per item)
      - error: error string key if detection failed
    """
    if "/stories/" in url:
        return {"type": "story", "entries": [], "error": None}

    loop = asyncio.get_event_loop()
    opts = {**_ig_base_opts(), "skip_download": True}

    def _extract():
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await loop.run_in_executor(None, _extract)
        if info is None:
            return {"type": "video", "entries": [], "error": "download_error"}

        if "/reel" in url or "/reels/" in url:
            return {"type": "reel", "entries": [info], "error": None}

        if info.get("_type") == "playlist":
            entries = info.get("entries") or []
            photos = [e for e in entries if e and _entry_is_photo(e)]
            if len(photos) == len(entries) and entries:
                return {"type": "carousel", "entries": entries, "error": None}
            return {"type": "carousel_mixed", "entries": entries, "error": None}

        if _entry_is_photo(info):
            return {"type": "photo", "entries": [info], "error": None}

        return {"type": "video", "entries": [info], "error": None}

    except yt_dlp.utils.DownloadError as e:
        raw = str(e)
        logger.warning("Instagram detection failed: %s", raw)
        error_key = classify_error(raw, "instagram")
        return {"type": "unknown", "entries": [], "error": error_key}
    except Exception as e:
        logger.error("Unexpected error during Instagram detection: %s", e)
        return {"type": "unknown", "entries": [], "error": "generic_error"}


async def download_instagram_photos(url: str, tmpdir: str, entries: list) -> list[str]:
    """Download photo(s) from Instagram, return list of local file paths."""
    loop = asyncio.get_event_loop()
    opts = {
        **_ig_base_opts(),
        "outtmpl": os.path.join(tmpdir, "%(autonumber)s_%(id)s.%(ext)s"),
        "format": "best",
    }

    def _download():
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

    await loop.run_in_executor(None, _download)

    image_exts = {".jpg", ".jpeg", ".webp", ".png"}
    files = sorted(
        [f for f in Path(tmpdir).iterdir() if f.suffix.lower() in image_exts],
        key=lambda p: p.name,
    )
    return [str(f) for f in files]


async def process_instagram_photos(message, user, url: str, status_msg) -> None:
    """Detect and handle Instagram photo/carousel/reel/story/video."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            ig_type_info = await detect_instagram_type(url)
            ig_type = ig_type_info["type"]
            error = ig_type_info.get("error")

            if error:
                await status_msg.edit_text(t(user.id, error))
                return

            if ig_type == "photo":
                await status_msg.edit_text(t(user.id, "ig_photo"))
                photos = await download_instagram_photos(url, tmpdir, ig_type_info["entries"])
                if not photos:
                    await status_msg.edit_text(t(user.id, "error_instagram"))
                    return
                await status_msg.edit_text(t(user.id, "ig_sending_photo"))
                with open(photos[0], "rb") as f:
                    await message.reply_photo(photo=f, read_timeout=60, write_timeout=60)
                await status_msg.edit_text(t(user.id, "done"))

            elif ig_type in ("carousel", "carousel_mixed"):
                entries = ig_type_info["entries"]
                count = len(entries)
                await status_msg.edit_text(t(user.id, "ig_carousel", count=count))
                photos = await download_instagram_photos(url, tmpdir, entries)
                if not photos:
                    await status_msg.edit_text(t(user.id, "error_instagram"))
                    return
                await status_msg.edit_text(t(user.id, "ig_sending_album"))
                image_exts = {".jpg", ".jpeg", ".webp", ".png"}
                photo_files = [p for p in photos if Path(p).suffix.lower() in image_exts]
                if photo_files:
                    BATCH = 10
                    for i in range(0, len(photo_files), BATCH):
                        batch = photo_files[i:i + BATCH]
                        media = []
                        handles = []
                        for path in batch:
                            fh = open(path, "rb")
                            handles.append(fh)
                            media.append(InputMediaPhoto(media=fh))
                        try:
                            await message.reply_media_group(
                                media=media, read_timeout=120, write_timeout=120
                            )
                        finally:
                            for fh in handles:
                                fh.close()
                await status_msg.edit_text(t(user.id, "done"))

            elif ig_type == "story":
                await status_msg.edit_text(t(user.id, "ig_story"))
                await _send_ig_video(url, tmpdir, message, user, status_msg)

            elif ig_type == "reel":
                await status_msg.edit_text(t(user.id, "ig_reel"))
                await _send_ig_video(url, tmpdir, message, user, status_msg)

            else:
                await status_msg.edit_text(t(user.id, "downloading"))
                await _send_ig_video(url, tmpdir, message, user, status_msg)

    except yt_dlp.utils.DownloadError as e:
        logger.error("Instagram download error: %s", e)
        await status_msg.edit_text(t(user.id, classify_error(str(e), "instagram")))
    except Exception as e:
        logger.error("Unexpected Instagram error: %s", e)
        await status_msg.edit_text(t(user.id, "generic_error"))


async def _send_ig_video(url: str, tmpdir: str, message, user, status_msg) -> None:
    """Download and send an Instagram video/reel/story."""
    loop = asyncio.get_event_loop()
    opts = {
        **_ig_base_opts(),
        "outtmpl": os.path.join(tmpdir, "%(title)s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "merge_output_format": "mp4",
    }

    def _download():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                return None
            filename = ydl.prepare_filename(info)
            path = Path(filename)
            if path.exists():
                return str(path)
            mp4 = path.with_suffix(".mp4")
            if mp4.exists():
                return str(mp4)
            files = [f for f in Path(tmpdir).iterdir() if f.is_file()]
            return str(files[0]) if files else None

    filepath = await loop.run_in_executor(None, _download)
    if not filepath or not Path(filepath).exists():
        await status_msg.edit_text(t(user.id, "error_instagram"))
        return

    if Path(filepath).stat().st_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await status_msg.edit_text(t(user.id, "too_large"))
        return

    await status_msg.edit_text(t(user.id, "sending"))
    with open(filepath, "rb") as f:
        await message.reply_video(
            video=f, supports_streaming=True, read_timeout=120, write_timeout=120
        )
    await status_msg.edit_text(t(user.id, "done"))


def build_ydl_opts(output_dir: str, fmt: str, quality: str, platform: str) -> dict:
    base: dict = {
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "retries": 1,
        "socket_timeout": 30,
        "http_headers": {"User-Agent": CHROME_USER_AGENT},
    }

    if Path(COOKIES_FILE).exists() and platform in ("instagram", "tiktok"):
        base["cookiefile"] = COOKIES_FILE

    if platform in ("tiktok", "instagram"):
        base["http_headers"] = {"User-Agent": TIKTOK_USER_AGENT}

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
    elif platform in ("tiktok", "instagram"):
        base.update({"format": "best[ext=mp4]/best", "merge_output_format": "mp4"})
    else:
        height_map = {"360": 360, "720": 720, "1080": 1080}
        if quality in height_map:
            h = height_map[quality]
            fmt_str = (
                f"best[ext=mp4][height<={h}][filesize<{MAX_FILE_SIZE_MB}M]"
                f"/best[height<={h}][filesize<{MAX_FILE_SIZE_MB}M]"
                f"/best[height<={h}]"
                f"/best[ext=mp4][filesize<{MAX_FILE_SIZE_MB}M]"
                f"/best[filesize<{MAX_FILE_SIZE_MB}M]"
                f"/best"
            )
        else:
            fmt_str = (
                f"best[ext=mp4][filesize<{MAX_FILE_SIZE_MB}M]"
                f"/best[filesize<{MAX_FILE_SIZE_MB}M]"
                f"/best"
            )
        base.update({"format": fmt_str, "merge_output_format": "mp4"})

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

    platform = detect_platform(url)

    if platform == "instagram":
        status_msg = await update.message.reply_text(
            t(user.id, "ig_detecting", user.language_code)
        )
        await process_instagram_photos(update.message, user, url, status_msg)
        return

    dl_id = uuid.uuid4().hex[:12]
    pending_downloads[dl_id] = {"url": url, "user_id": user.id, "platform": platform}

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
    platform = pending_downloads[dl_id].get("platform", "unknown")

    if fmt == "video" and platform == "youtube":
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
