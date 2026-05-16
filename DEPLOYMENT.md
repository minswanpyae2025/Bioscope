# Bioscope Telegram Bot Deployment Guide

This guide covers the deployment of the two-part system:
1. **Main Bot:** Hosted on Render (handles users, UI, API, database logic).
2. **Leecher Bot (WZML-X Modified):** Hosted on a VPS (handles downloading and uploading heavy files).

---

## 1. Supabase (Database) Setup
1. Create a new project on [Supabase](https://supabase.com/).
2. Go to the SQL Editor in your Supabase dashboard.
3. Copy the contents of the `database_schema.sql` file provided in the repository.
4. Paste it into the SQL Editor and click **Run** to create all required tables.
5. Go to **Project Settings > API** and copy your:
   - **Project URL**
   - **anon/public key**

---

## 2. Redis Setup
You need a Redis instance for communication between the Main Bot and the Leecher.
- You can use [Upstash](https://upstash.com/) for a free Serverless Redis.
- Create a database and copy the **Redis Connection URL** (e.g., `rediss://default:password@endpoint:port`).

---

## 3. Main Bot Setup (Render)

1. Create a new **Web Service** or **Background Worker** on Render.
2. Connect it to your GitHub repository, pointing the Root Directory to `main_bot` (if configured that way, or just the root repo and update start command).
3. Set the environment variables in Render:
   - `BOT_TOKEN`: Your Main Bot token from BotFather.
   - `SUPABASE_URL`: Your Supabase Project URL.
   - `SUPABASE_KEY`: Your Supabase anon/public key.
   - `REDIS_URL`: Your Redis connection string.
   - `ADMIN_ID`: Your Telegram User ID.
   - `BIOSCOPE_EMAIL`: Email for your scraper.
   - `BIOSCOPE_PASS`: Password for your scraper.
   - `TZ`: `Asia/Yangon`
4. Build command: `pip install -r requirements.txt`
5. Start command: `python3 bot.py`
6. Deploy the service. The Main Bot will now handle user requests and push download jobs to Redis.

---

## 4. Leecher Bot Setup (VPS / WZML-X)

The WZML-X bot in this repository has been modified to listen to the Redis queue.

1. Follow the standard WZML-X VPS deployment steps (from the main README).
2. Generate your Telegram User Session using the provided script:
   `python3 generate_session.py`
3. Before starting the bot, add the following to your `config.env` (or Docker environment variables):
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - `REDIS_URL`
   - `LEECHER_DUMP_CHAT_ID`: The ID of the Dump Channel (e.g., `-100123456789`).
   - `USER_SESSION_STRING`: The string generated in step 2.
4. Deploy WZML-X.
5. The bot will automatically start a background thread that listens to Redis for new URLs to leech. When it finishes, it updates Supabase.

---

## Post-Deployment Actions
1. Message your Main Bot and use `/start`.
2. As the Admin, configure the Dump Channel and Trash Channel using the bot's admin commands (`/set_dump_channel`, `/set_trash_channel`, `/set_required_channels`, `/add_ad`) or directly in the Supabase `admin_config` table.
