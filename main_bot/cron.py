import os
import asyncio
from telegram import Bot
from db import supabase, get_admin_config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_dead_links():
    bot = Bot(token=os.environ.get("BOT_TOKEN"))
    trash_id = get_admin_config("trash_channel_id")
    dump_id = get_admin_config("dump_channel_id")

    if not trash_id or not dump_id: return

    res = supabase.table("videos").select("*").eq("is_alive", True).execute()
    for video in res.data:
        try:
            msg_id = video["dump_message_id"]
            if not msg_id: continue
            await bot.forward_message(chat_id=trash_id, from_chat_id=dump_id, message_id=msg_id)
            supabase.table("videos").update({"last_checked": "now()"}).eq("id", video["id"]).execute()
        except Exception:
            logger.warning(f"Video {video['id']} is dead. Attempting auto-heal...")
            supabase.table("videos").update({"is_alive": False}).eq("id", video["id"]).execute()

            # Auto Heal Logic
            try:
                from scraper import BioscopeInteractiveScraper
                import json
                import asyncio
                import os
                import redis

                # Use local scraper to fetch fresh stream payload
                scraper = BioscopeInteractiveScraper()
                scraper.login()

                is_movie = (video['type'] == 'movie')
                streams = []
                if is_movie:
                    streams = scraper.get_movie_streams(video['post_id'])
                else:
                    streams = scraper.get_tv_streams(video['post_id'])

                target_stream = None
                for s in streams:
                    if s.get('resolution') == video['resolution']:
                        target_stream = s
                        break

                if not target_stream:
                    raise Exception(f"No stream found for resolution {video['resolution']}")

                url = scraper.extract_stream_url(target_stream, video['post_id'], is_movie)
                if not url:
                    raise Exception("Stream URL extraction failed.")

                # Push back to queue silently
                r = redis.from_url(os.environ.get("REDIS_URL"), decode_responses=True)

                # Create a dummy system request so it gets processed
                req_ins = supabase.table("user_requests").insert({"user_id": int(os.environ.get("ADMIN_ID", "0")), "video_id": video["id"], "status": "queued"}).execute()
                req_id = req_ins.data[0]['id']

                payload = {"internal_video_id": video["id"], "url": url, "req_id": req_id}
                r.lpush("leech_queue", json.dumps(payload))
                logger.info(f"Auto-heal triggered for video {video['id']}")

            except Exception as e:
                logger.error(f"Auto-heal failed for video {video['id']}: {e}")
                # Notify admin
                try:
                    admin_id = int(os.environ.get("ADMIN_ID", "0"))
                    if admin_id:
                        await bot.send_message(chat_id=admin_id, text=f"⚠️ **Auto-Heal Failed**\nVideo ID: {video['id']}\nPost ID: {video['post_id']}\nResolution: {video['resolution']}\nError: {e}")
                except Exception as ex:
                    logger.error(f"Failed to notify admin: {ex}")

        await asyncio.sleep(2)

async def monitor_completed_requests():
    bot = Bot(token=os.environ.get("BOT_TOKEN"))
    dump_id = get_admin_config("dump_channel_id")

    while True:
        try:
            res = supabase.table("user_requests").select("*, videos(*)").eq("status", "uploaded").execute()
            for req in res.data:
                user_id = req["user_id"]
                vid = req["videos"]
                if vid and vid.get("dump_message_id"):
                    try:
                        title = vid.get("title", "Bioscope Video")
                        await bot.copy_message(chat_id=user_id, from_chat_id=dump_id, message_id=vid["dump_message_id"], caption=f"**{title}**\n\n@BioscopeBot", parse_mode="Markdown", protect_content=True)
                        supabase.table("user_requests").update({"status": "completed"}).eq("id", req["id"]).execute()
                    except Exception as e:
                        logger.error(f"Could not send video to user {user_id}: {e}")
        except Exception as e:
             logger.error(f"Monitor error: {e}")
        await asyncio.sleep(10)

def start_background_monitors():
    from cron import check_dead_links, monitor_completed_requests
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def run_cron():
        while True:
            await check_dead_links()
            await asyncio.sleep(3600) # Every hour

    loop.create_task(run_cron())
    loop.create_task(monitor_completed_requests())
    loop.run_forever()
