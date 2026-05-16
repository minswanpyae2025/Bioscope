from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import json
from db import supabase, get_admin_config
import logging
from datetime import datetime
import pytz
from dateutil.parser import parse
from db import redis_client

logger = logging.getLogger(__name__)

# Redis rate limit configurations
RATE_LIMIT_ACTIONS = 10
RATE_LIMIT_SECONDS = 60
START_COMMAND_COOLDOWN = 10

async def is_rate_limited(user_id: int, action_type: str = "general") -> bool:
    if not redis_client:
        return False

    if action_type == "start":
        key = f"rate_limit:start:{user_id}"
        if redis_client.exists(key):
            return True
        redis_client.setex(key, START_COMMAND_COOLDOWN, 1)
        return False
    else:
        key = f"rate_limit:general:{user_id}"
        current_count = redis_client.get(key)
        if current_count and int(current_count) >= RATE_LIMIT_ACTIONS:
            return True

        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, RATE_LIMIT_SECONDS)
        pipe.execute()
        return False

async def check_force_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    req_ch_raw = get_admin_config("required_channels", "[]")

    try:
        req_channels = json.loads(req_ch_raw) if isinstance(req_ch_raw, str) else req_ch_raw
    except:
        req_channels = []

    if not req_channels: return True

    # Check cache
    if supabase:
        user_res = supabase.table("users").select("joined_check_cache").eq("id", user_id).execute()
        if user_res.data:
            cache_str = user_res.data[0].get("joined_check_cache")
            if cache_str:
                cache_time = parse(cache_str)
                if (datetime.now(pytz.utc) - cache_time).total_seconds() < 300:
                    return True

    to_join = []
    for ch in req_channels:
        try:
            member = await context.bot.get_chat_member(chat_id=ch, user_id=user_id)
            if member.status in ['left', 'kicked']:
                to_join.append(ch)
        except Exception as e:
            logger.error(f"Force join check failed for {ch}: {e}")

    if to_join:
        return False

    if supabase:
        supabase.table("users").update({"joined_check_cache": "now()"}).eq("id", user_id).execute()
    return True

async def force_join_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user: return

    user_id = update.effective_user.id

    # Check rate limits
    if update.message and update.message.text and update.message.text.startswith('/start'):
        if await is_rate_limited(user_id, "start"):
            raise Exception("RateLimitedStart")

    # Check general rate limits
    if await is_rate_limited(user_id, "general"):
        warning_msg = "⚠️ သင်ဟာ အသုံးပြုမှုမြန်ဆန်နေပါတယ်။ ခဏစောင့်ပြီးမှ ထပ်မံကြိုးစားပါ။"
        if update.message:
            await update.message.reply_text(warning_msg)
        elif update.callback_query:
            try:
                await update.callback_query.answer(warning_msg, show_alert=True)
            except:
                await update.callback_query.message.reply_text(warning_msg)
        raise Exception("RateLimitedGeneral")

    if update.message and update.message.text and update.message.text.startswith('/'):
        return

    if update.callback_query and update.callback_query.data == "check_joined":
        pass
    else:
        passed = await check_force_join(update, context)
        if not passed:
            req_ch_raw = get_admin_config("required_channels", "[]")
            import json
            channels = json.loads(req_ch_raw) if isinstance(req_ch_raw, str) else req_ch_raw
            kb = []
            for ch in channels:
                kb.append([InlineKeyboardButton(f"Join Channel", url=f"https://t.me/{str(ch).replace('-100', '')}")])
            kb.append([InlineKeyboardButton("✅ စစ်ဆေးမည်", callback_data="check_joined")])

            if update.message:
                await update.message.reply_text("❗ ကျေးဇူးပြု၍ အောက်ပါချန်နယ်များကို Join ပါ။", reply_markup=InlineKeyboardMarkup(kb))
            elif update.callback_query:
                await update.callback_query.edit_message_text("❗ ကျေးဇူးပြု၍ အောက်ပါချန်နယ်များကို Join ပါ။", reply_markup=InlineKeyboardMarkup(kb))
            raise Exception("ForceJoinStop")
