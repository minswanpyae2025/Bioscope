import os
import json
import asyncio
import logging
from threading import Thread
import redis
from supabase import create_client, Client
from bot import bot, config_dict
from bot.helper.telegram_helper.message_utils import sendFile
from bot.helper.ext_utils.bot_utils import new_task
from bot.modules.leech import leech

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
REDIS_URL = os.environ.get("REDIS_URL", "")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

redis_client = None
if REDIS_URL:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)

class DummyMessage:
    def __init__(self, url):
        self.text = f"/leech {url}"
        import random; self.message_id = random.randint(100000, 999999)
        self.id = self.message_id
        self.chat = type('Chat', (object,), {'id': int(os.environ.get("LEECHER_DUMP_CHAT_ID", "-1000000000000")), 'type': 'channel'})
        self.from_user = type('User', (object,), {'id': 12345})
        self.reply_to_message = None

    async def reply_text(self, *args, **kwargs):
        return type('Message', (object,), {'id': 111111, 'delete': self._dummy_async, 'edit_text': self._dummy_async, 'reply_to_message': None})()

    async def reply(self, *args, **kwargs):
        return await self.reply_text(*args, **kwargs)

    async def _dummy_async(self, *args, **kwargs):
        pass

async def process_queue():
    if not redis_client or not supabase:
        logger.info("Redis or Supabase not configured for Leecher Worker.")
        return

    logger.info("Starting Redis Worker to listen for 'leech_queue'...")
    while True:
        try:
            item = await asyncio.to_thread(redis_client.blpop, "leech_queue", timeout=0)
            if item:
                data = json.loads(item[1])
                url = data.get("url")
                internal_video_id = data.get("internal_video_id")
                req_id = data.get("req_id")
                if not url: continue
                dummy_msg = DummyMessage(url)
                redis_client.set(f"active_leech_{dummy_msg.message_id}", json.dumps({"internal_video_id": internal_video_id, "req_id": req_id}))

                # Execute in the main bot_loop!
                from bot import bot_loop
                asyncio.run_coroutine_threadsafe(leech(bot, dummy_msg), bot_loop)
        except Exception as e:
            logger.error(f"Redis worker error: {e}")
            await asyncio.sleep(5)

def start_redis_worker_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(process_queue())

def init_worker():
    t = Thread(target=start_redis_worker_thread, daemon=True)
    t.start()
