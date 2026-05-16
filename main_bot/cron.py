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
            supabase.table("videos").update({"is_alive": False}).eq("id", video["id"]).execute()
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
                        await bot.copy_message(chat_id=user_id, from_chat_id=dump_id, message_id=vid["dump_message_id"])
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
