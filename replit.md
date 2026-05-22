# Telegram Video Downloader Bot

A Python Telegram bot that downloads videos from YouTube, Instagram, and TikTok using yt-dlp and sends them back to the user.

## Run & Operate

- `python bot/bot.py` — run the Telegram bot
- Required env: `TELEGRAM_BOT_TOKEN` — Telegram bot token from @BotFather

## Stack

- Python 3.11
- python-telegram-bot — Telegram Bot API wrapper
- yt-dlp — video downloading from YouTube, Instagram, TikTok
- ffmpeg — video processing/merging

## Where things live

- `bot/bot.py` — main bot entry point, all handlers and download logic

## Architecture decisions

- Uses `tempfile.TemporaryDirectory` so downloaded files are cleaned up automatically after sending
- Download runs in a thread executor to avoid blocking the async event loop
- File size capped at 50MB (Telegram bot API limit)
- Supports YouTube, Instagram, TikTok URLs; rejects others with a clear message

## Product

Users send a YouTube, Instagram, or TikTok video link to the bot in Telegram. The bot downloads the video and sends it back as a Telegram video message. Supports `/start` for a welcome message.

## User preferences

- _Populate as needed_

## Gotchas

- Telegram bot API has a 50MB file size limit for video uploads
- yt-dlp may occasionally fail on private/geo-restricted content
- ffmpeg must be installed as a system dep for video merging to work

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
