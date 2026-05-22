import os
import asyncio
import logging
import tempfile
import re
from pathlib import Path

import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

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

URL_PATTERN = re.compile(
    r"https?://[^\s]+"
)

MAX_FILE_SIZE_MB = 50


def is_supported_url(url: str) -> bool:
    return any(domain in url for domain in SUPPORTED_DOMAINS)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Hello! I'm a video downloader bot.\n\n"
        "Send me a video link from:\n"
        "• YouTube\n"
        "• Instagram\n"
        "• TikTok\n\n"
        "I'll download and send the video back to you!"
    )


async def download_video(url: str, output_dir: str) -> str | None:
    ydl_opts = {
        "format": "bestvideo[ext=mp4][filesize<50M]+bestaudio[ext=m4a]/best[ext=mp4][filesize<50M]/best",
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "max_filesize": MAX_FILE_SIZE_MB * 1024 * 1024,
    }

    loop = asyncio.get_event_loop()

    def _download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                return None
            filename = ydl.prepare_filename(info)
            path = Path(filename)
            if not path.exists():
                mp4_path = path.with_suffix(".mp4")
                if mp4_path.exists():
                    return str(mp4_path)
                files = list(Path(output_dir).glob("*"))
                if files:
                    return str(files[0])
                return None
            return str(path)

    return await loop.run_in_executor(None, _download)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    urls = URL_PATTERN.findall(text)

    if not urls:
        await update.message.reply_text(
            "Please send a valid video URL from YouTube, Instagram, or TikTok."
        )
        return

    url = urls[0]

    if not is_supported_url(url):
        await update.message.reply_text(
            "⚠️ Unsupported platform. Please send a link from YouTube, Instagram, or TikTok."
        )
        return

    status_msg = await update.message.reply_text("⏳ Downloading your video, please wait...")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = await download_video(url, tmpdir)

            if filepath is None or not Path(filepath).exists():
                await status_msg.edit_text(
                    "❌ Failed to download the video. The link may be private, expired, or unsupported."
                )
                return

            file_size = Path(filepath).stat().st_size
            if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
                await status_msg.edit_text(
                    f"❌ Video is too large to send (over {MAX_FILE_SIZE_MB}MB). "
                    "Try a shorter or lower-quality video."
                )
                return

            await status_msg.edit_text("📤 Sending video...")

            with open(filepath, "rb") as video_file:
                await update.message.reply_video(
                    video=video_file,
                    supports_streaming=True,
                    read_timeout=120,
                    write_timeout=120,
                )

            await status_msg.delete()

    except yt_dlp.utils.DownloadError as e:
        logger.error("Download error: %s", e)
        await status_msg.edit_text(
            "❌ Could not download the video. It may be private, geo-restricted, or the link is invalid."
        )
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        await status_msg.edit_text(
            "❌ Something went wrong while processing your request. Please try again."
        )


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
