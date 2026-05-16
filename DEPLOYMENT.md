# Bioscope Bot Deployment Guide

This project consists of a two-tier Telegram bot architecture designed for high performance, security, and scalability.

1.  **Main Bot (`main_bot/`):** The user-facing Telegram bot that handles UI, inline keyboards, rate limiting, Supabase database interactions, and user queues.
2.  **Worker Bot / WZML-X (`bot/`):** A modified background worker that listens to Redis queues, downloads media, uploads to Telegram, and publishes status events back to Redis via Pub/Sub.

---

## Prerequisites

Before deploying either bot, you must set up the following external services:

1.  **Telegram Bot Token:** Obtain a bot token from [@BotFather](https://t.me/BotFather) on Telegram.
2.  **Supabase (PostgreSQL):** Create a project on [Supabase](https://supabase.com). Run the SQL commands in `database_schema.sql` to initialize your database structure. Retrieve your `SUPABASE_URL` and `SUPABASE_KEY` (anon/public key).
3.  **Redis:** Create a Redis database (e.g., via Redis Labs, Upstash, or host your own). Retrieve the `REDIS_URL` (e.g., `redis://username:password@host:port`).

---

## Tier 1: Deploying the Main Bot (Render, Heroku, or Local)

The Main Bot handles all user interactions and must be always online. Render is recommended for easy deployment.

### Required Environment Variables

*   `BOT_TOKEN`: Your Telegram Bot Token.
*   `SUPABASE_URL`: Your Supabase Project URL.
*   `SUPABASE_KEY`: Your Supabase API Key.
*   `REDIS_URL`: Your Redis Connection URL.
*   `TZ`: Your Timezone (e.g., `Asia/Yangon`).
*   `BIOSCOPE_EMAIL`: (Optional) Scraper account email.
*   `BIOSCOPE_PASS`: (Optional) Scraper account password.

### Deploying on Render (via Web Service or Background Worker)

1.  Create a new **Web Service** or **Background Worker** on Render connected to your repository.
2.  **Build Command:** `pip install -r main_bot/requirements.txt`
3.  **Start Command:** `cd main_bot && python bot.py`
4.  Add the environment variables listed above.
5.  Deploy!

### Running Locally

1.  Navigate to the `main_bot` directory: `cd main_bot`
2.  Install dependencies: `pip install -r requirements.txt`
3.  Export your environment variables (or use a `.env` file if you install `python-dotenv`).
4.  Run the bot: `python bot.py`

---

## Tier 2: Deploying the Worker Bot (VPS)

The Worker Bot (WZML-X) does the heavy lifting: downloading torrents/direct links and uploading them to Telegram. Because of the heavy bandwidth and storage requirements, it must be deployed on a VPS or a robust local machine using Docker.

### Required Environment Variables (in `config.env`)

You must create a `config.env` file in the root of the repository for the worker bot. You can use `config_sample.py` as a reference, but the core additions required for this architecture are:

*   `BOT_TOKEN`: Your Telegram Bot Token (Same as Main Bot).
*   `OWNER_ID`: Your Telegram User ID.
*   `TELEGRAM_API`: Your Telegram API ID from `my.telegram.org`.
*   `TELEGRAM_HASH`: Your Telegram API Hash from `my.telegram.org`.
*   `DATABASE_URL`: Your PostgreSQL connection string (can be obtained from Supabase).
*   `REDIS_URL`: Your Redis Connection URL (Same as Main Bot).
*   `SUPABASE_URL`: Your Supabase Project URL.
*   `SUPABASE_KEY`: Your Supabase API Key.
*   `LEECHER_DUMP_CHAT_ID`: The ID of the private channel where the bot uploads videos (e.g., `-1001234567890`). Ensure the bot is an admin in this channel.

### Deploying on a VPS (using Docker)

1.  Clone the repository on your VPS.
2.  Create your `config.env` file with the variables above.
3.  Make sure Docker and Docker Compose are installed on your VPS.
4.  Build and run the Docker image:
    ```bash
    sudo docker-compose up -d --build
    ```
5.  Check the logs to ensure the worker connected to Redis successfully:
    ```bash
    sudo docker-compose logs -f
    ```

### Architecture Flow

1.  **User Request:** User clicks a movie resolution in the Main Bot.
2.  **Queueing:** Main Bot limits the user, checks tier, updates Supabase, and pushes a payload to `vip_queue` or `leech_queue` in Redis.
3.  **Worker Processing:** The Worker Bot (VPS) continuously listens to `vip_queue` and `leech_queue`. It picks up the task, downloads the video, and uploads it to the `LEECHER_DUMP_CHAT_ID`.
4.  **Completion Hook:** Upon upload completion, the Worker Bot publishes an `upload_complete` event with the Telegram `file_id` and `message_id` to the `wzmlx_events` Redis Pub/Sub channel.
5.  **Final Delivery:** The Main Bot receives the `upload_complete` event, updates the video cache in Supabase, and forwards the video from the dump channel to the user with an inline rating keyboard.
