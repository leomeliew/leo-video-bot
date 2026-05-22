# leo-video-bot

A Telegram bot that downloads videos from YouTube, Instagram, and TikTok using [yt-dlp](https://github.com/yt-dlp/yt-dlp) and sends them back to the user.

## Features

- Download videos from YouTube, Instagram, TikTok
- Quality selection for YouTube (360p / 720p / 1080p / Best)
- Format selection: Video (MP4), MP3 audio, Voice message (OGG)
- Multi-language support: English, Russian, Uzbek (auto-detected)
- Retry logic with platform-specific error messages
- Cookie support for Instagram authenticated content

## Setup

1. Clone the repo
2. Install dependencies:
   ```
   pip install python-telegram-bot yt-dlp
   ```
3. Install ffmpeg (required for audio extraction and merging)
4. Set your bot token:
   ```
   export TELEGRAM_BOT_TOKEN=your_token_here
   ```
5. Run:
   ```
   python bot/bot.py
   ```

## Commands

- `/start` - welcome message
- `/language` - switch language (English / Russian / Uzbek)

## Notes

- Telegram bot API limit is 50MB per file
- Drop a `bot/cookies.txt` (Netscape format) to enable Instagram authenticated downloads