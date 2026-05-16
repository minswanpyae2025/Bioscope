import re

# 1. Fix cron.py to use copy_message with protect_content=True
with open("main_bot/cron.py", "r") as f:
    cron_content = f.read()

cron_content = cron_content.replace(
    "await bot.forward_message(chat_id=trash_id, from_chat_id=dump_id, message_id=msg_id)",
    "await bot.copy_message(chat_id=trash_id, from_chat_id=dump_id, message_id=msg_id, protect_content=True)"
)

# Also add the Redis listener to cron.py
redis_listener_code = r"""
async def listen_redis_webhooks():
    import redis.asyncio as redis
    import json
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url: return
    r = redis.from_url(redis_url, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe("supabase_updates")
    logger.info("Listening to Redis Pub/Sub for supabase_updates...")
    async for message in pubsub.listen():
        if message["type"] == "message":
            try:
                data = json.loads(message["data"])
                if data.get("type") == "video_uploaded":
                    internal_video_id = data["internal_video_id"]
                    req_id = data["req_id"]
                    file_id = data["file_id"]
                    dump_msg_id = data["dump_msg_id"]
                    supabase.table("videos").update({
                        "telegram_file_id": file_id,
                        "dump_message_id": dump_msg_id,
                        "is_alive": True
                    }).eq("id", internal_video_id).execute()
                    supabase.table("user_requests").update({"status": "uploaded"}).eq("id", req_id).execute()
            except Exception as e:
                logger.error(f"Error processing webhook: {e}")
"""

start_monitor_regex = r"(loop\.create_task\(monitor_completed_requests\(\)\))"
start_monitor_replacement = r"\1\n    loop.create_task(listen_redis_webhooks())"

cron_content = cron_content.replace("from cron import check_dead_links, monitor_completed_requests", "from cron import check_dead_links, monitor_completed_requests, listen_redis_webhooks")

with open("main_bot/cron.py", "w") as f:
    f.write(redis_listener_code + "\n" + cron_content.replace("loop.create_task(monitor_completed_requests())", "loop.create_task(monitor_completed_requests())\n    loop.create_task(listen_redis_webhooks())"))
