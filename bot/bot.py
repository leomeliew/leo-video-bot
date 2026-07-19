import os
import sys
import fcntl
import asyncio
import logging
import tempfile
import re
import json
import uuid
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import subprocess
import imageio_ffmpeg
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

# ffmpeg binary provided by imageio-ffmpeg — no system ffmpeg required
_FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

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
LOCK_FILE = "/tmp/telegram_bot.lock"
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# Admin state: users currently waiting to send a cookies.txt document
_awaiting_cookies: set[int] = set()

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
MOBILE_UA = "TikTok 26.2.0 rv:262018 (iPhone; iOS 14.4.2; en_US) Cronet"

IMAGE_EXTS = {".jpg", ".jpeg", ".webp", ".png", ".gif"}
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi"}

# ── Strings ───────────────────────────────────────────────────────────────────

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "start": (
            "👋 Hello! I'm a video downloader bot.\n\n"
            "Send me a link from:\n"
            "• YouTube\n"
            "• Instagram (photos, carousels, videos, reels, stories)\n"
            "• TikTok\n\n"
            "I'll download and send it back!\n\n"
            "Use /language to change language."
        ),
        "choose_language": "🌐 Choose your language:",
        "language_set": "✅ Language set to English.",
        "choose_format": "🎞 Choose format:",
        "choose_quality": "📺 Choose video quality:",
        "downloading": "⏳ Downloading, please wait...",
        "downloading_retry": "⏳ Retrying (attempt {attempt}/{max})...",
        "sending": "📤 Sending...",
        "done": "✅ Done!",
        "too_large": f"❌ File exceeds {MAX_FILE_SIZE_MB} MB. Try lower quality or a shorter clip.",
        "download_error": "❌ Could not download. The link may be private, expired, or unsupported.",
        "error_private": "🔒 This content is private. Only public posts can be downloaded.",
        "error_geo": "🌍 This video is geo-restricted and not available here.",
        "error_removed": "🚫 This content has been removed or is no longer available.",
        "error_youtube": "❌ YouTube download failed. Video may be age-restricted or unavailable.",
        "error_instagram": "❌ Instagram download failed. Only public posts are supported.",
        "error_tiktok": "❌ TikTok download failed. Video may be removed or restricted.",
        "generic_error": "❌ Something went wrong. Please try again.",
        "unsupported": "⚠️ Unsupported platform. Send a YouTube, Instagram, or TikTok link.",
        "no_url": "Please send a valid URL from YouTube, Instagram, or TikTok.",
        "fmt_video": "🎬 Video (MP4)",
        "fmt_mp3": "🎵 MP3",
        "fmt_voice": "🎙 Voice",
        "q_360": "360p",
        "q_720": "720p",
        "q_1080": "1080p",
        "q_best": "⭐ Best",
        "cancelled": "❌ Cancelled.",
        "ig_detecting": "🔍 Detecting content type...",
        "ig_photo": "📷 Downloading photo...",
        "ig_carousel": "🖼 Downloading album ({count} items)...",
        "ig_sending_photo": "📤 Sending photo...",
        "ig_sending_album": "📤 Sending album...",
        "cookie_send_file": "📎 Send cookies.txt as a document.",
        "cookie_updated": "✅ Cookie yangilandi!",
        "cookie_not_admin": "⛔ You are not authorized to use this command.",
        "cookie_not_file": "❌ Please send a file named cookies.txt.",
    },
    "ru": {
        "start": (
            "👋 Привет! Я бот для скачивания контента.\n\n"
            "Отправь мне ссылку с:\n"
            "• YouTube\n"
            "• Instagram (фото, карусели, видео, рилсы, истории)\n"
            "• TikTok\n\n"
            "Я скачаю и пришлю!\n\n"
            "Используй /language для смены языка."
        ),
        "choose_language": "🌐 Выберите язык:",
        "language_set": "✅ Язык изменён на Русский.",
        "choose_format": "🎞 Выберите формат:",
        "choose_quality": "📺 Выберите качество видео:",
        "downloading": "⏳ Скачиваю, подождите...",
        "downloading_retry": "⏳ Повторная попытка ({attempt}/{max})...",
        "sending": "📤 Отправляю...",
        "done": "✅ Готово!",
        "too_large": f"❌ Файл больше {MAX_FILE_SIZE_MB} МБ. Попробуйте меньшее качество.",
        "download_error": "❌ Не удалось скачать. Ссылка приватная, устарела или не поддерживается.",
        "error_private": "🔒 Контент приватный. Доступны только публичные публикации.",
        "error_geo": "🌍 Видео недоступно в вашем регионе (geo-ограничение).",
        "error_removed": "🚫 Контент удалён или больше не доступен.",
        "error_youtube": "❌ Ошибка YouTube. Видео может быть с возрастным ограничением.",
        "error_instagram": "❌ Ошибка Instagram. Доступны только публичные публикации.",
        "error_tiktok": "❌ Ошибка TikTok. Видео удалено или ограничено.",
        "generic_error": "❌ Что-то пошло не так. Попробуйте ещё раз.",
        "unsupported": "⚠️ Неподдерживаемая платформа. Отправьте ссылку YouTube, Instagram или TikTok.",
        "no_url": "Отправьте корректную ссылку с YouTube, Instagram или TikTok.",
        "fmt_video": "🎬 Видео (MP4)",
        "fmt_mp3": "🎵 MP3",
        "fmt_voice": "🎙 Голосовое",
        "q_360": "360p",
        "q_720": "720p",
        "q_1080": "1080p",
        "q_best": "⭐ Лучшее",
        "cancelled": "❌ Отменено.",
        "ig_detecting": "🔍 Определяю тип контента...",
        "ig_photo": "📷 Скачиваю фото...",
        "ig_carousel": "🖼 Скачиваю альбом ({count} элементов)...",
        "ig_sending_photo": "📤 Отправляю фото...",
        "ig_sending_album": "📤 Отправляю альбом...",
        "cookie_send_file": "📎 Отправьте cookies.txt файл как документ.",
        "cookie_updated": "✅ Cookie yangilandi!",
        "cookie_not_admin": "⛔ У вас нет прав для этой команды.",
        "cookie_not_file": "❌ Пожалуйста, отправьте файл с именем cookies.txt.",
    },
    "uz": {
        "start": (
            "👋 Salom! Men kontent yuklovchi botman.\n\n"
            "Menga havola yuboring:\n"
            "• YouTube\n"
            "• Instagram (rasmlar, karusellar, videolar, reelslar, hikoyalar)\n"
            "• TikTok\n\n"
            "Men yuklab, sizga yuboraman!\n\n"
            "Til uchun /language buyrug'ini ishlating."
        ),
        "choose_language": "🌐 Tilni tanlang:",
        "language_set": "✅ Til O'zbek tiliga o'zgartirildi.",
        "choose_format": "🎞 Formatni tanlang:",
        "choose_quality": "📺 Video sifatini tanlang:",
        "downloading": "⏳ Yuklanmoqda, iltimos kuting...",
        "downloading_retry": "⏳ Qayta urinish ({attempt}/{max})...",
        "sending": "📤 Yuborilmoqda...",
        "done": "✅ Tayyor!",
        "too_large": f"❌ Fayl {MAX_FILE_SIZE_MB} MB dan katta. Pastroq sifatni sinab ko'ring.",
        "download_error": "❌ Yuklab bo'lmadi. Havola shaxsiy, muddati o'tgan yoki qo'llab-quvvatlanmaydi.",
        "error_private": "🔒 Bu kontent shaxsiy. Faqat ochiq postlar yuklab olinadi.",
        "error_geo": "🌍 Bu video sizning mintaqangizda mavjud emas.",
        "error_removed": "🚫 Bu kontent o'chirilgan yoki mavjud emas.",
        "error_youtube": "❌ YouTube xatosi. Video yosh cheklovi yoki mavjud emaslik tufayli.",
        "error_instagram": "❌ Instagram xatosi. Faqat ochiq postlar qo'llab-quvvatlanadi.",
        "error_tiktok": "❌ TikTok xatosi. Video o'chirilgan yoki cheklangan.",
        "generic_error": "❌ Xato yuz berdi. Iltimos qaytadan urinib ko'ring.",
        "unsupported": "⚠️ Qo'llab-quvvatlanmaydi. YouTube, Instagram yoki TikTok havolasini yuboring.",
        "no_url": "YouTube, Instagram yoki TikTok dan to'g'ri havola yuboring.",
        "fmt_video": "🎬 Video (MP4)",
        "fmt_mp3": "🎵 MP3",
        "fmt_voice": "🎙 Ovozli",
        "q_360": "360p",
        "q_720": "720p",
        "q_1080": "1080p",
        "q_best": "⭐ Eng yaxshi",
        "cancelled": "❌ Bekor qilindi.",
        "ig_detecting": "🔍 Kontent turi aniqlanmoqda...",
        "ig_photo": "📷 Rasm yuklanmoqda...",
        "ig_carousel": "🖼 Albom yuklanmoqda ({count} element)...",
        "ig_sending_photo": "📤 Rasm yuborilmoqda...",
        "ig_sending_album": "📤 Albom yuborilmoqda...",
        "cookie_send_file": "📎 cookies.txt faylini dokument sifatida yuboring.",
        "cookie_updated": "✅ Cookie yangilandi!",
        "cookie_not_admin": "⛔ Siz bu buyruqdan foydalana olmaysiz.",
        "cookie_not_file": "❌ Iltimos, cookies.txt nomli fayl yuboring.",
    },
}

LANG_DETECT_MAP = {"ru": "ru", "uz": "uz", "uk": "ru"}

# ── In-memory state ───────────────────────────────────────────────────────────

pending_downloads: dict[str, dict] = {}

# ── Lock (prevent duplicate instances) ───────────────────────────────────────

_lock_fh = None  # keep fd alive so lock is held

def acquire_instance_lock() -> None:
    global _lock_fh
    try:
        _lock_fh = open(LOCK_FILE, "w")
        fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_fh.write(str(os.getpid()))
        _lock_fh.flush()
        logger.info("Instance lock acquired (PID %s)", os.getpid())
    except IOError:
        logger.error("Another bot instance is already running — exiting.")
        sys.exit(0)

# ── User data helpers ─────────────────────────────────────────────────────────

def load_user_data() -> dict:
    if Path(USER_DATA_FILE).exists():
        with open(USER_DATA_FILE) as f:
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
    data.setdefault(uid, {})["lang"] = lang
    save_user_data(data)


def t(user_id: int, key: str, telegram_lang: str | None = None, **kwargs) -> str:
    lang = get_user_lang(user_id, telegram_lang)
    text = STRINGS.get(lang, STRINGS["en"]).get(key, STRINGS["en"].get(key, key))
    return text.format(**kwargs) if kwargs else text

# ── URL helpers ───────────────────────────────────────────────────────────────

def is_supported_url(url: str) -> bool:
    return any(d in url for d in SUPPORTED_DOMAINS)


def detect_platform(url: str) -> str:
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    if "instagram.com" in url:
        return "instagram"
    if "tiktok.com" in url:
        return "tiktok"
    return "unknown"


def classify_error(msg: str, platform: str) -> str:
    m = msg.lower()
    if any(k in m for k in ("private", "login", "sign in", "authentication", "requires auth")):
        return "error_private"
    if any(k in m for k in ("geo", "not available in your country", "region")):
        return "error_geo"
    if any(k in m for k in ("removed", "no longer available", "deleted", "does not exist", "404")):
        return "error_removed"
    return {"youtube": "error_youtube", "instagram": "error_instagram", "tiktok": "error_tiktok"}.get(
        platform, "download_error"
    )

# ── yt-dlp option builders ────────────────────────────────────────────────────

def _cookies_opts(platform: str) -> dict:
    """Return cookiefile option ONLY for Instagram and TikTok."""
    if platform in ("instagram", "tiktok") and Path(COOKIES_FILE).exists():
        return {"cookiefile": COOKIES_FILE}
    return {}


def _ig_base_opts(output_dir: str | None = None) -> dict:
    """Base yt-dlp options for Instagram (and TikTok)."""
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "http_headers": {"User-Agent": MOBILE_UA},
        **_cookies_opts("instagram"),
    }
    if output_dir:
        opts["outtmpl"] = os.path.join(output_dir, "%(autonumber)s_%(id)s.%(ext)s")
    return opts


def build_ydl_opts(output_dir: str, fmt: str, quality: str, platform: str) -> dict:
    base: dict = {
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "retries": 1,
        "socket_timeout": 30,
        "http_headers": {"User-Agent": CHROME_UA},
        **_cookies_opts(platform),
    }

    if platform in ("tiktok", "instagram"):
        base["http_headers"] = {"User-Agent": MOBILE_UA}

    if fmt == "mp3":
        # Download best audio directly — no postprocessor needed; send file as-is
        base.update({"format": "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio"})
    elif fmt == "voice":
        # Download best audio; pydub converts to OGG Opus after download
        base.update({"format": "bestaudio[ext=m4a]/bestaudio[ext=opus]/bestaudio"})
    elif platform in ("tiktok", "instagram"):
        base.update({"format": "best[ext=mp4]/best", "merge_output_format": "mp4"})
    else:
        h_map = {"360": 360, "720": 720, "1080": 1080}
        if quality in h_map:
            h = h_map[quality]
            fmt_str = (
                f"best[ext=mp4][height<={h}][filesize<{MAX_FILE_SIZE_MB}M]"
                f"/best[height<={h}][filesize<{MAX_FILE_SIZE_MB}M]"
                f"/best[height<={h}]/best[ext=mp4][filesize<{MAX_FILE_SIZE_MB}M]"
                f"/best[filesize<{MAX_FILE_SIZE_MB}M]/best"
            )
        else:
            fmt_str = (
                f"best[ext=mp4][filesize<{MAX_FILE_SIZE_MB}M]"
                f"/best[filesize<{MAX_FILE_SIZE_MB}M]/best"
            )
        base.update({"format": fmt_str, "merge_output_format": "mp4"})

    return base


def _find_output_file(output_dir: str, prepared_path: str, fmt: str) -> str | None:
    p = Path(prepared_path)

    if fmt in ("mp3", "voice"):
        # bestaudio can produce m4a, mp3, opus, ogg, webm — accept any audio file
        audio_exts = (".m4a", ".mp3", ".opus", ".ogg", ".webm", ".aac", ".flac")
        for ext in audio_exts:
            c = p.with_suffix(ext)
            if c.exists():
                return str(c)
        for pat in [f"*{e}" for e in audio_exts]:
            matches = list(Path(output_dir).glob(pat))
            if matches:
                return str(matches[0])
    else:
        for c in [p, p.with_suffix(".mp4")]:
            if c.exists():
                return str(c)

    files = [f for f in Path(output_dir).iterdir() if f.is_file()]
    return str(files[0]) if files else None

# ── Download helpers ──────────────────────────────────────────────────────────

async def download_file(
    url: str, output_dir: str, fmt: str, quality: str, platform: str
) -> tuple[str | None, str | None, dict]:
    """Download a single file. Returns (filepath, error_key, meta)."""
    last_error: str | None = None
    loop = asyncio.get_event_loop()

    for attempt in range(1, MAX_RETRIES + 1):
        opts = build_ydl_opts(output_dir, fmt, quality, platform)
        _meta_holder: list[dict] = [{}]

        def _dl(o=opts, holder=_meta_holder):
            with yt_dlp.YoutubeDL(o) as ydl:
                info = ydl.extract_info(url, download=True)
                if info:
                    holder[0] = {
                        "title": info.get("title") or info.get("fulltitle") or "",
                        "performer": (
                            info.get("artist")
                            or info.get("creator")
                            or info.get("uploader")
                            or ""
                        ),
                    }
                return ydl.prepare_filename(info) if info else None

        try:
            prepared = await loop.run_in_executor(None, _dl)
            meta = _meta_holder[0]
            if prepared is None:
                last_error = "no_info"
                continue
            fp = _find_output_file(output_dir, prepared, fmt)
            if fp:
                return fp, None, meta
            last_error = "file_not_found"

        except yt_dlp.utils.DownloadError as e:
            raw = str(e)
            logger.warning("Download attempt %d/%d failed (%s): %s", attempt, MAX_RETRIES, platform, raw)
            last_error = raw
            key = classify_error(raw, platform)
            if key in ("error_private", "error_removed", "error_geo"):
                return None, key, {}
        except Exception as e:
            logger.error("Unexpected error attempt %d: %s", attempt, e)
            last_error = str(e)

        if attempt < MAX_RETRIES:
            await asyncio.sleep(2 * attempt)

    return None, classify_error(last_error or "", platform) if last_error else "download_error", {}


def _is_photo_entry(entry: dict) -> bool:
    """Return True when a yt-dlp info entry represents a still image, not video."""
    vcodec = entry.get("vcodec", "") or ""
    ext = (entry.get("ext", "") or "").lower()
    if vcodec.lower() in ("none", ""):
        return True
    if ext in ("jpg", "jpeg", "webp", "png", "gif"):
        return True
    return False

# ── Instagram detection + handling ───────────────────────────────────────────

async def _ig_extract_info(url: str) -> dict | None:
    """Run yt-dlp extract_info (no download) in executor."""
    loop = asyncio.get_event_loop()
    opts = {**_ig_base_opts(), "skip_download": True}

    def _run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    return await loop.run_in_executor(None, _run)


async def detect_instagram_type(url: str) -> dict:
    """
    Detect Instagram content type.
    Returns {"type": str, "entries": list, "error": str|None}

    Possible types: "photo", "carousel", "video", "reel", "story"
    """
    try:
        info = await _ig_extract_info(url)
    except yt_dlp.utils.DownloadError as e:
        return {"type": "unknown", "entries": [], "error": classify_error(str(e), "instagram")}
    except Exception as e:
        logger.error("IG detection error: %s", e)
        return {"type": "unknown", "entries": [], "error": "generic_error"}

    if info is None:
        return {"type": "unknown", "entries": [], "error": "error_instagram"}

    # Story URLs always treated as story
    if "/stories/" in url:
        return {"type": "story", "entries": [info], "error": None}

    # Reel URLs always treated as video reel
    if "/reel/" in url or "/reels/" in url:
        return {"type": "reel", "entries": [info], "error": None}

    # Playlist → carousel (could be mixed photo+video)
    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        return {"type": "carousel", "entries": entries, "error": None}

    # Single item
    if _is_photo_entry(info):
        return {"type": "photo", "entries": [info], "error": None}

    return {"type": "video", "entries": [info], "error": None}


async def _download_ig_photos(url: str, tmpdir: str) -> list[str]:
    """Download Instagram content and return sorted list of image file paths."""
    loop = asyncio.get_event_loop()
    opts = {
        **_ig_base_opts(tmpdir),
        "format": "best",
    }

    def _dl():
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

    await loop.run_in_executor(None, _dl)
    return sorted(
        [str(f) for f in Path(tmpdir).iterdir() if f.suffix.lower() in IMAGE_EXTS],
        key=lambda p: Path(p).name,
    )


async def _download_ig_video(url: str, tmpdir: str) -> tuple[str | None, dict]:
    """Download Instagram video/reel/story. Returns (filepath, meta)."""
    loop = asyncio.get_event_loop()
    opts = {
        **_ig_base_opts(tmpdir),
        "format": "best[ext=mp4]/best",
        "merge_output_format": "mp4",
    }
    _meta_holder: list[dict] = [{}]

    def _dl():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                return None
            _meta_holder[0] = {
                "title": info.get("title") or info.get("fulltitle") or "",
                "performer": info.get("uploader") or info.get("creator") or "",
            }
            p = Path(ydl.prepare_filename(info))
            if p.exists():
                return str(p)
            mp4 = p.with_suffix(".mp4")
            if mp4.exists():
                return str(mp4)
            files = [f for f in Path(tmpdir).iterdir() if f.is_file()]
            return str(files[0]) if files else None

    path = await loop.run_in_executor(None, _dl)
    return path, _meta_holder[0]


async def _convert_audio_ffmpeg(src_path: str, fmt: str) -> str | None:
    """
    Convert audio/video to MP3 or OGG Opus via imageio-ffmpeg binary (no system ffmpeg needed).
    fmt="mp3"   → 192 kbps MP3
    fmt="voice" → OGG Opus 128 kbps (Telegram voice message)
    Returns output path or None on failure.
    """
    loop = asyncio.get_event_loop()
    src = Path(src_path)

    if fmt == "mp3":
        out = str(src.parent / (src.stem + "_audio.mp3"))
        cmd = [_FFMPEG_BIN, "-y", "-i", str(src), "-vn", "-acodec", "libmp3lame", "-q:a", "2", out]
    else:  # voice → OGG Opus
        out = str(src.parent / (src.stem + "_voice.ogg"))
        cmd = [_FFMPEG_BIN, "-y", "-i", str(src), "-vn", "-c:a", "libopus", "-b:a", "128k", out]

    def _run():
        result = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120
        )
        if result.returncode != 0:
            logger.warning("ffmpeg %s conversion failed: %s", fmt, result.stderr.decode()[-300:])
            return None
        p = Path(out)
        return str(p) if p.exists() and p.stat().st_size > 0 else None

    return await loop.run_in_executor(None, _run)


async def process_instagram_media(message, user, url: str, fmt: str, status_msg) -> None:
    """
    Full Instagram handler. Detects type, then:
      - photo/carousel → download images, send as photo(s), ignore fmt
      - video/reel/story → download with requested fmt (video/mp3/voice)
    """
    try:
        ig = await detect_instagram_type(url)

        if ig["error"]:
            await status_msg.edit_text(t(user.id, ig["error"]))
            return

        ig_type = ig["type"]

        with tempfile.TemporaryDirectory() as tmpdir:

            # ── Photos / Carousels ─────────────────────────────────────────
            if ig_type in ("photo", "carousel"):
                count = len(ig["entries"]) if ig["entries"] else 1
                if ig_type == "carousel":
                    await status_msg.edit_text(t(user.id, "ig_carousel", count=count))
                else:
                    await status_msg.edit_text(t(user.id, "ig_photo"))

                photos = await _download_ig_photos(url, tmpdir)

                if not photos:
                    await status_msg.edit_text(t(user.id, "error_instagram"))
                    return

                if len(photos) == 1:
                    await status_msg.edit_text(t(user.id, "ig_sending_photo"))
                    with open(photos[0], "rb") as f:
                        await message.reply_photo(photo=f, read_timeout=60, write_timeout=60)
                else:
                    await status_msg.edit_text(t(user.id, "ig_sending_album"))
                    BATCH = 10
                    for i in range(0, len(photos), BATCH):
                        batch = photos[i : i + BATCH]
                        handles = [open(p, "rb") for p in batch]
                        media = [InputMediaPhoto(media=fh) for fh in handles]
                        try:
                            await message.reply_media_group(
                                media=media, read_timeout=120, write_timeout=120
                            )
                        finally:
                            for fh in handles:
                                fh.close()

                await status_msg.edit_text(t(user.id, "done"))
                return

            # ── Videos / Reels / Stories ───────────────────────────────────
            # Instagram has no separate audio stream — always download video first,
            # then extract audio with ffmpeg (bestaudio/best fails for Instagram).
            if fmt in ("mp3", "voice"):
                await status_msg.edit_text(t(user.id, "downloading"))
                video_path, meta = await _download_ig_video(url, tmpdir)
                if not video_path or not Path(video_path).exists():
                    await status_msg.edit_text(t(user.id, "error_instagram"))
                    return
                audio_path = await _convert_audio_ffmpeg(video_path, fmt)
                if not audio_path:
                    await status_msg.edit_text(t(user.id, "download_error"))
                    return
                await status_msg.edit_text(t(user.id, "sending"))
                with open(audio_path, "rb") as f:
                    if fmt == "mp3":
                        await message.reply_audio(
                            audio=f,
                            title=meta.get("title") or None,
                            performer=meta.get("performer") or None,
                            read_timeout=120,
                            write_timeout=120,
                        )
                    else:
                        await message.reply_voice(voice=f, read_timeout=120, write_timeout=120)
                await status_msg.edit_text(t(user.id, "done"))
                return

            # Default: download video
            await status_msg.edit_text(t(user.id, "downloading"))
            filepath, _ = await _download_ig_video(url, tmpdir)

            if not filepath or not Path(filepath).exists():
                # Maybe it's actually a photo (e.g. story with image)
                photos = [str(f) for f in Path(tmpdir).iterdir() if f.suffix.lower() in IMAGE_EXTS]
                if photos:
                    await status_msg.edit_text(t(user.id, "ig_sending_photo"))
                    with open(photos[0], "rb") as f:
                        await message.reply_photo(photo=f, read_timeout=60, write_timeout=60)
                    await status_msg.edit_text(t(user.id, "done"))
                    return
                await status_msg.edit_text(t(user.id, "error_instagram"))
                return

            fsize = Path(filepath).stat().st_size
            if fsize > MAX_FILE_SIZE_MB * 1024 * 1024:
                await status_msg.edit_text(t(user.id, "too_large"))
                return

            await status_msg.edit_text(t(user.id, "sending"))
            with open(filepath, "rb") as f:
                await message.reply_video(
                    video=f, supports_streaming=True, read_timeout=120, write_timeout=120
                )
            await status_msg.edit_text(t(user.id, "done"))

    except yt_dlp.utils.DownloadError as e:
        logger.error("IG download error: %s", e)
        await status_msg.edit_text(t(user.id, classify_error(str(e), "instagram")))
    except Exception as e:
        logger.error("Unexpected IG error: %s", e)
        await status_msg.edit_text(t(user.id, "generic_error"))

# ── Keyboards ─────────────────────────────────────────────────────────────────

def format_keyboard(user_id: int, dl_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(user_id, "fmt_video"), callback_data=f"fmt:video:{dl_id}"),
            InlineKeyboardButton(t(user_id, "fmt_mp3"),   callback_data=f"fmt:mp3:{dl_id}"),
            InlineKeyboardButton(t(user_id, "fmt_voice"), callback_data=f"fmt:voice:{dl_id}"),
        ],
    ])


def quality_keyboard(user_id: int, dl_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(user_id, "q_360"),  callback_data=f"q:360:{dl_id}"),
            InlineKeyboardButton(t(user_id, "q_720"),  callback_data=f"q:720:{dl_id}"),
        ],
        [
            InlineKeyboardButton(t(user_id, "q_1080"), callback_data=f"q:1080:{dl_id}"),
            InlineKeyboardButton(t(user_id, "q_best"), callback_data=f"q:best:{dl_id}"),
        ],
    ])


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇬🇧 English",  callback_data="lang:en"),
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang:ru"),
        InlineKeyboardButton("🇺🇿 O'zbek",  callback_data="lang:uz"),
    ]])

# ── Handlers ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(t(user.id, "start", user.language_code))


async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(
        t(user.id, "choose_language", user.language_code),
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
    dl_id = uuid.uuid4().hex[:12]

    if platform == "instagram":
        # Detect content type first; show format buttons only for video/reel/story
        status_msg = await update.message.reply_text(
            t(user.id, "ig_detecting", user.language_code)
        )
        ig = await detect_instagram_type(url)

        if ig["error"]:
            await status_msg.edit_text(t(user.id, ig["error"]))
            return

        ig_type = ig["type"]

        if ig_type in ("photo", "carousel"):
            # No format selection needed — send photos directly
            pending_downloads[dl_id] = {
                "url": url, "user_id": user.id, "platform": "instagram",
                "ig_type": ig_type, "ig_entries": ig["entries"], "fmt": "video",
            }
            await process_instagram_media(update.message, user, url, "video", status_msg)
            pending_downloads.pop(dl_id, None)
            return

        # Video / reel / story: show format buttons
        pending_downloads[dl_id] = {
            "url": url, "user_id": user.id, "platform": "instagram",
            "ig_type": ig_type,
        }
        await status_msg.edit_text(
            t(user.id, "choose_format", user.language_code),
            reply_markup=format_keyboard(user.id, dl_id),
        )
        return

    # YouTube / TikTok → show format buttons immediately
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

    entry = pending_downloads[dl_id]
    entry["fmt"] = fmt
    platform = entry.get("platform", "unknown")

    if platform == "instagram":
        # Hand off to Instagram-specific handler
        url = entry["url"]
        ig_type = entry.get("ig_type", "video")
        status_msg = query.message  # edit this message for status updates
        pending_downloads.pop(dl_id, None)
        await query.edit_message_text(t(user.id, "ig_detecting"))
        await process_instagram_media(query.message, user, url, fmt, query.message)
        return

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
    """Handle YouTube and TikTok downloads (not Instagram)."""
    entry = pending_downloads.pop(dl_id, None)
    if not entry:
        await query.edit_message_text(t(user.id, "cancelled"))
        return

    url = entry["url"]
    fmt = entry.get("fmt", "video")
    platform = detect_platform(url)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath: str | None = None
            error_key: str | None = None

            for attempt in range(1, MAX_RETRIES + 1):
                if attempt > 1:
                    try:
                        await query.edit_message_text(
                            t(user.id, "downloading_retry", attempt=attempt, max=MAX_RETRIES)
                        )
                    except Exception:
                        pass
                    await asyncio.sleep(2 * (attempt - 1))

                filepath, error_key, meta = await download_file(url, tmpdir, fmt, quality, platform)
                if filepath is not None:
                    break
                if error_key in ("error_private", "error_removed", "error_geo"):
                    await query.edit_message_text(t(user.id, error_key))
                    return
                if attempt == MAX_RETRIES:
                    await query.edit_message_text(t(user.id, error_key or "download_error"))
                    return

            if not filepath or not Path(filepath).exists():
                await query.edit_message_text(t(user.id, "download_error"))
                return

            if Path(filepath).stat().st_size > MAX_FILE_SIZE_MB * 1024 * 1024:
                await query.edit_message_text(t(user.id, "too_large"))
                return

            await query.edit_message_text(t(user.id, "sending"))

            # Voice: convert downloaded audio to OGG Opus via ffmpeg
            if fmt == "voice":
                converted = await _convert_audio_ffmpeg(filepath, "voice")
                if converted:
                    filepath = converted

            with open(filepath, "rb") as f:
                if fmt == "mp3":
                    await query.message.reply_audio(
                        audio=f,
                        title=meta.get("title") or None,
                        performer=meta.get("performer") or None,
                        read_timeout=120,
                        write_timeout=120,
                    )
                elif fmt == "voice":
                    await query.message.reply_voice(voice=f, read_timeout=120, write_timeout=120)
                else:
                    await query.message.reply_video(
                        video=f, supports_streaming=True, read_timeout=120, write_timeout=120
                    )

            await query.edit_message_text(t(user.id, "done"))

    except Exception as e:
        logger.error("Unexpected error in process_download: %s", e)
        await query.edit_message_text(t(user.id, "generic_error"))

# ── Entry point ───────────────────────────────────────────────────────────────

async def _post_init(app: Application) -> None:
    """Run before polling starts: evict any lingering Telegram session."""
    await asyncio.sleep(5)          # let the old process fully release the session
    for attempt in range(1, 4):
        try:
            await app.bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook cleared (attempt %d), starting polling…", attempt)
            return
        except Exception as e:
            logger.warning("delete_webhook attempt %d failed: %s", attempt, e)
            await asyncio.sleep(3)


async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler — log all errors; ignore transient Conflict errors."""
    from telegram.error import Conflict
    err = context.error
    if isinstance(err, Conflict):
        logger.warning("Transient Conflict error (ignoring): %s", err)
        return
    logger.error("Unhandled bot error: %s", err, exc_info=err)


async def cmd_updatecookies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not ADMIN_ID or user.id != ADMIN_ID:
        await update.message.reply_text(t(user.id, "cookie_not_admin"))
        return
    _awaiting_cookies.add(user.id)
    await update.message.reply_text(t(user.id, "cookie_send_file"))


async def handle_cookies_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id not in _awaiting_cookies:
        return
    doc = update.message.document
    if not doc or not doc.file_name or not doc.file_name.lower().endswith(".txt"):
        await update.message.reply_text(t(user.id, "cookie_not_file"))
        return
    _awaiting_cookies.discard(user.id)
    file = await doc.get_file()
    await file.download_to_drive(COOKIES_FILE)
    logger.info("cookies.txt updated by admin %s", user.id)
    await update.message.reply_text(t(user.id, "cookie_updated"))


def main() -> None:
    acquire_instance_lock()

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set")

    app = (
        Application.builder()
        .token(token)
        .post_init(_post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("language", cmd_language))
    app.add_handler(CommandHandler("updatecookies", cmd_updatecookies))
    app.add_handler(CallbackQueryHandler(handle_language_callback, pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(handle_format_callback,   pattern=r"^fmt:"))
    app.add_handler(CallbackQueryHandler(handle_quality_callback,  pattern=r"^q:"))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_cookies_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(_error_handler)

    # Keepalive HTTP server so Replit doesn't sleep the instance
    class _PingHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        def log_message(self, *args):
            pass

    threading.Thread(
        target=lambda: HTTPServer(("0.0.0.0", 8082), _PingHandler).serve_forever(),
        daemon=True,
    ).start()
    logger.info("Keepalive server started on port 8082")

    logger.info("Bot starting…")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
