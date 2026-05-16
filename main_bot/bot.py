import os
import sys
import json
import logging
import asyncio
import uuid
from datetime import datetime, timedelta
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes, TypeHandler
)

from scraper import BioscopeInteractiveScraper
from db import supabase, redis_client, get_admin_config
from middleware import force_join_middleware
from admin import set_dump_channel, set_trash_channel, set_required_channels, add_ad

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

scraper = BioscopeInteractiveScraper()
if not scraper.login():
    logger.error("Scraper login failed. Exiting.")

TZ = pytz.timezone(os.environ.get("TZ", "Asia/Yangon"))
STREAM_CACHE = {}

async def get_or_create_user(user_id, username, first_name):
    if not supabase: return None
    res = supabase.table("users").select("*").eq("id", user_id).execute()
    if not res.data:
        data = {"id": user_id, "username": username, "first_name": first_name, "tier": "free", "daily_requests_used": 0, "streak_days": 0, "last_activity_date": datetime.now(TZ).date().isoformat()}
        res = supabase.table("users").insert(data).execute()
        return res.data[0]
    return res.data[0]

async def update_user_activity_and_streak(user):
    now = datetime.now(TZ).date()
    last_act = user.get("last_activity_date")
    updates = {"last_activity_date": now.isoformat()}

    if last_act:
        last_act_date = datetime.fromisoformat(last_act).date()
        if last_act_date == now - timedelta(days=1):
            streak = user.get("streak_days", 0) + 1
            if streak >= 7:
                reward_hours = int(get_admin_config("streak_reward_premium_hours", 24))
                new_expires = datetime.now(TZ) + timedelta(hours=reward_hours)
                updates["streak_days"] = 0
                updates["premium_expires_at"] = new_expires.isoformat()
                updates["tier"] = "premium"
            else:
                updates["streak_days"] = streak
        elif last_act_date < now - timedelta(days=1):
            updates["streak_days"] = 1
            updates["daily_requests_used"] = 0

    if not last_act or last_act_date < now:
         updates["daily_requests_used"] = 0

    supabase.table("users").update(updates).eq("id", user["id"]).execute()

def get_main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 ရုပ်ရှင်အသစ်များ", callback_data="movies")],
        [InlineKeyboardButton("📺 ဇာတ်လမ်းတွဲအသစ်များ", callback_data="tvshows")],
        [InlineKeyboardButton("🔍 ရုပ်ရှင်ရှာရန်", callback_data="search_movies")],
        [InlineKeyboardButton("🔎 ဇာတ်လမ်းတွဲရှာရန်", callback_data="search_tv")],
        [InlineKeyboardButton("⭐ သင့်အတွက်", callback_data="for_you")],
        [InlineKeyboardButton("🔥 ယနေ့လူကြိုက်အများဆုံး", callback_data="top_24h")],
        [InlineKeyboardButton("👤 ပရိုဖိုင်", callback_data="profile")],
    ])

async def invite_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{update.effective_user.id}"
    await update.message.reply_text(f"🎁 သူငယ်ချင်းများကို ဖိတ်ခေါ်ပြီး Token ရယူပါ:\n`{link}`", parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].startswith("ref_"):
        inviter_id = int(context.args[0].split("_")[1])
        if inviter_id != update.effective_user.id:
            try:
                supabase.table("invites").insert({"inviter_id": inviter_id, "invitee_id": update.effective_user.id}).execute()
                tok_res = supabase.table("tokens").select("balance").eq("user_id", inviter_id).execute()
                balance = tok_res.data[0]['balance'] if tok_res.data else 0
                supabase.table("tokens").upsert({"user_id": inviter_id, "balance": balance + 5}).execute()
            except: pass

    user = update.effective_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    if db_user: await update_user_activity_and_streak(db_user)

    await update.message.reply_text("🎬 *Bioscope Bot မှ ကြိုဆိုပါတယ်*\nအောက်ပါ Menu မှ ရွေးချယ်ပါ:", reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "check_joined":
        from middleware import check_force_join
        passed = await check_force_join(update, context)
        if passed:
            await query.edit_message_text("🎬 *Bioscope Bot Menu*:", reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
        else:
            await query.answer("မဝင်ရသေးပါ", show_alert=True)
        return

    if data == "movies": await show_movies_list(query)
    elif data == "tvshows": await show_tvshows_list(query)
    elif data == "main_menu": await query.edit_message_text("🎬 *Bioscope Bot Menu*:", reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
    elif data == "search_movies":
        context.user_data['search_type'] = 'movie'
        await query.edit_message_text("🔍 ရှာဖွေလိုသော ရုပ်ရှင်အမည်ကို ရိုက်ထည့်ပါ:")
    elif data == "search_tv":
        context.user_data['search_type'] = 'tv'
        await query.edit_message_text("🔎 ရှာဖွေလိုသော ဇာတ်လမ်းတွဲအမည်ကို ရိုက်ထည့်ပါ:")
    elif data == "profile": await show_profile(query, update.effective_user.id)
    elif data == "for_you": await query.edit_message_text("သင်ဟာဒါကို ကြည့်ဖူးလို့ ဒါကိုလဲ ကြည့်ကြည့်ပါလား\n(မကြာမီလာမည်)")
    elif data == "top_24h": await show_top_24h(query)
    elif data.startswith("movie_"): await handle_movie_request(query, data.split("_")[1])
    elif data.startswith("tvshow_"): await show_episodes(query, data.split("_")[1])
    elif data.startswith("episode_"): await handle_tv_request(query, data.split("_")[1], int(data.split("_")[2]))
    elif data.startswith("sel_"): await process_tier_check_and_ad(query, update.effective_user.id, data.split("_")[1])
    elif data.startswith("ad_watched_"):
        parts = data.split("_")
        reward_tokens = int(parts[-2])
        uid = int(parts[-1])
        payload = parts[2]
        tok_res = supabase.table("tokens").select("balance").eq("user_id", uid).execute()
        balance = tok_res.data[0]['balance'] if tok_res.data else 0
        supabase.table("tokens").upsert({"user_id": uid, "balance": balance + reward_tokens}).execute()
        await query.message.delete()
        await process_video_request(query, uid, payload)

async def show_movies_list(query):
    res = await asyncio.to_thread(scraper.browse_movies)
    movies = res.get("data", [])[:30]
    if not movies:
        await query.edit_message_text("❌ မတွေ့ရှိပါ။")
        return
    buttons = [[InlineKeyboardButton(m.get("title", "Unknown"), callback_data=f"movie_{m['id']}")] for m in movies]
    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")])
    await query.edit_message_text("🎬 *ရုပ်ရှင်အသစ်များ* (ရွေးချယ်ပါ):", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def show_tvshows_list(query):
    res = await asyncio.to_thread(scraper.browse_tv_shows)
    shows = res.get("data", [])[:30]
    if not shows:
        await query.edit_message_text("❌ မတွေ့ရှိပါ။")
        return
    buttons = [[InlineKeyboardButton(s.get("title", "Unknown"), callback_data=f"tvshow_{s['id']}")] for s in shows]
    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")])
    await query.edit_message_text("📺 *ဇာတ်လမ်းတွဲအသစ်များ* (ရွေးချယ်ပါ):", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stype = context.user_data.get('search_type')
    kw = update.message.text
    if stype == 'movie':
        res = await asyncio.to_thread(scraper.search_movies, kw)
        items = res.get("data", [])[:30]
        buttons = [[InlineKeyboardButton(m.get("title", "Unknown"), callback_data=f"movie_{m['id']}")] for m in items]
        buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")])
        await update.message.reply_text("🎬 *ရှာဖွေမှုရလဒ်များ*:", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
    elif stype == 'tv':
        res = await asyncio.to_thread(scraper.search_tv_shows, kw)
        items = res.get("data", [])[:30]
        buttons = [[InlineKeyboardButton(s.get("title", "Unknown"), callback_data=f"tvshow_{s['id']}")] for s in items]
        buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")])
        await update.message.reply_text("📺 *ရှာဖွေမှုရလဒ်များ*:", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def show_episodes(query, tv_id):
    episodes = await asyncio.to_thread(scraper.get_tv_episodes, tv_id)
    if not episodes:
        await query.edit_message_text("❌ မတွေ့ရှိပါ။")
        return
    buttons = [[InlineKeyboardButton(f"Episode {ep.get('episode_number', '?')} – {ep.get('title', 'Unknown')}", callback_data=f"episode_{tv_id}_{idx}")] for idx, ep in enumerate(episodes)]
    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="tvshows")])
    await query.edit_message_text("📺 အပိုင်းရွေးချယ်ပါ:", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def handle_movie_request(query, movie_id):
    await query.edit_message_text("🔄 စစ်ဆေးနေပါသည်...")
    streams = await asyncio.to_thread(scraper.get_movie_streams, movie_id)
    if not streams:
        await query.edit_message_text("❌ မတွေ့ရှိပါ။")
        return
    buttons = []
    for idx, s in enumerate(streams):
        res = s.get('resolution', 'Unknown')
        size = s.get('size', 'Unknown')
        cache_id = str(uuid.uuid4())[:8]
        STREAM_CACHE[cache_id] = {"stream": s, "post_id": movie_id, "is_movie": True}
        buttons.append([InlineKeyboardButton(f"🎬 {res} | {size} (Option {idx+1})", callback_data=f"sel_{cache_id}")])
    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="movies")])
    await query.edit_message_text("🎬 **ရုပ်ရှင်အရည်အသွေး ရွေးချယ်ပါ:**", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def handle_tv_request(query, tv_id, ep_idx):
    await query.edit_message_text("🔄 စစ်ဆေးနေပါသည်...")
    episodes = await asyncio.to_thread(scraper.get_tv_episodes, tv_id)
    if not episodes or ep_idx >= len(episodes):
        await query.edit_message_text("❌ မတွေ့ရှိပါ။")
        return
    target_ep_id = episodes[ep_idx].get("id")
    streams = await asyncio.to_thread(scraper.get_tv_streams, target_ep_id)
    if not streams:
        await query.edit_message_text("❌ မတွေ့ရှိပါ။")
        return
    buttons = []
    for idx, s in enumerate(streams):
        res = s.get('resolution', 'Unknown')
        size = s.get('size', 'Unknown')
        cache_id = str(uuid.uuid4())[:8]
        STREAM_CACHE[cache_id] = {"stream": s, "post_id": target_ep_id, "is_movie": False, "tv_id": tv_id}
        buttons.append([InlineKeyboardButton(f"📺 {res} | {size} (Option {idx+1})", callback_data=f"sel_{cache_id}")])
    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data=f"tvshow_{tv_id}")])
    await query.edit_message_text("📺 **အရည်အသွေး ရွေးချယ်ပါ:**", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def process_tier_check_and_ad(query, user_id, cache_id):
    res = supabase.table("users").select("*").eq("id", user_id).execute()
    if not res.data: return
    user = res.data[0]

    if user['tier'] == 'premium' and user.get('premium_expires_at'):
        if datetime.now(TZ) > datetime.fromisoformat(user['premium_expires_at']):
            user['tier'] = 'free'
            supabase.table("users").update({"tier": "free", "premium_expires_at": None}).eq("id", user_id).execute()

    is_premium = user['tier'] == 'premium'
    limit = int(get_admin_config(f"{user['tier']}_daily_limit", 5 if not is_premium else 50))

    if user['daily_requests_used'] >= limit:
         await query.edit_message_text("❌ ယနေ့အတွက် သတ်မှတ်ထားသော အရေအတွက် ပြည့်သွားပါပြီ။")
         return

    if is_premium:
        await process_video_request(query, user_id, cache_id)
    else:
        tok_res = supabase.table("tokens").select("balance").eq("user_id", user_id).execute()
        balance = tok_res.data[0]['balance'] if tok_res.data else 0
        if balance > 0:
            supabase.table("tokens").update({"balance": balance - 1}).eq("user_id", user_id).execute()
            await process_video_request(query, user_id, cache_id)
        else:
            ad_req = get_admin_config("ad_watch_required", True)
            if str(ad_req).lower() == 'true':
                default_ad_id = get_admin_config("default_ad_id")
                if default_ad_id:
                    ad_res = supabase.table("ads").select("*").eq("id", int(default_ad_id)).execute()
                    if ad_res.data:
                        ad = ad_res.data[0]
                        sec = ad['required_watch_seconds']
                        text = f"{ad['text']}\n\n⏳ ကြော်ငြာကို {sec} စက္ကန့် ကြည့်ရှုပြီးမှ ဆက်လုပ်နိုင်ပါမည်။"
                        buttons = []
                        if ad['inline_link'] and ad['inline_link'] != "#": buttons.append([InlineKeyboardButton("🔗 Visit Link", url=ad['inline_link'])])
                        buttons.append([InlineKeyboardButton(f"⏳ Please wait {sec}s...", callback_data="ignore")])
                        try:
                            msg = await query.message.reply_video(video=ad['video_file_id'], caption=text, reply_markup=InlineKeyboardMarkup(buttons))
                            asyncio.create_task(enable_ad_button(msg, cache_id, sec, ad['reward_tokens'], user_id))
                            await query.message.delete()
                            return
                        except: pass

                msg = await query.edit_message_text("⏳ ကြော်ငြာကို ၁၀ စက္ကန့် ကြည့်ရှုပြီးမှ ဆက်လုပ်နိုင်ပါမည်။\n(Loading Ad...)")
                buttons = [[InlineKeyboardButton("⏳ Please wait 10s...", callback_data="ignore")]]
                await query.edit_message_reply_markup(InlineKeyboardMarkup(buttons))
                asyncio.create_task(enable_ad_button(query.message, cache_id, 10, 5, user_id))
            else:
                await process_video_request(query, user_id, cache_id)

async def enable_ad_button(message, payload, sec, reward_tokens, user_id):
    await asyncio.sleep(sec)
    buttons = [[InlineKeyboardButton("✅ ဆက်လုပ်ရန်", callback_data=f"ad_watched_{payload}_{reward_tokens}_{user_id}")]]
    try: await message.edit_reply_markup(InlineKeyboardMarkup(buttons))
    except: pass

async def process_video_request(query, user_id, cache_id):
    if cache_id not in STREAM_CACHE:
        await query.edit_message_text("❌ သက်တမ်းကုန်သွားပါသည်။ ကျေးဇူးပြု၍ ပြန်လည်ရွေးချယ်ပါ။")
        return

    s_data = STREAM_CACHE[cache_id]
    target_stream = s_data["stream"]
    post_id = s_data["post_id"]
    is_movie = s_data["is_movie"]

    await query.edit_message_text("🔄 စစ်ဆေးနေပါသည်...")

    res = supabase.table("users").select("daily_requests_used").eq("id", user_id).execute()
    used = res.data[0]['daily_requests_used'] + 1
    supabase.table("users").update({"daily_requests_used": used}).eq("id", user_id).execute()

    source_id = f"{post_id}_{target_stream.get('id')}"
    v_type = "movie" if is_movie else "tv_episode"

    v_res = supabase.table("videos").select("*").eq("source_id", source_id).eq("type", v_type).execute()

    if v_res.data and v_res.data[0].get("is_alive") and v_res.data[0].get("telegram_file_id"):
        dump_channel = get_admin_config("dump_channel_id")
        msg_id = v_res.data[0]["dump_message_id"]
        try:
            await query.bot.copy_message(chat_id=user_id, from_chat_id=dump_channel, message_id=msg_id)
            await query.edit_message_text("✅ ပို့ဆောင်ပြီးပါပြီ။")
            await asyncio.sleep(3)
            await query.message.delete()
            return
        except Exception as e:
            logger.error(f"Copy message failed: {e}")
            supabase.table("videos").update({"is_alive": False}).eq("id", v_res.data[0]["id"]).execute()

    await query.edit_message_text("📥 ဒေါင်းလုဒ်စတင်နေပါပြီ...")
    url = await asyncio.to_thread(scraper.extract_stream_url, target_stream, post_id, is_movie)

    if not url:
        await query.edit_message_text("❌ Error getting stream.")
        return

    internal_id = v_res.data[0]['id'] if v_res.data else None
    if not internal_id:
        ins = supabase.table("videos").insert({"source_id": source_id, "type": v_type}).execute()
        internal_id = ins.data[0]['id']

    req_ins = supabase.table("user_requests").insert({"user_id": user_id, "video_id": internal_id, "status": "queued"}).execute()
    req_id = req_ins.data[0]['id']

    if redis_client:
        payload = {"internal_video_id": internal_id, "url": url, "req_id": req_id}
        redis_client.lpush("leech_queue", json.dumps(payload))

    await query.edit_message_text("📥 တန်းစီထားပါသည်။ ခေတ္တစောင့်ဆိုင်းပေးပါ။")

async def show_top_24h(query):
    yesterday = (datetime.now(TZ) - timedelta(days=1)).isoformat()
    res = supabase.table("user_requests").select("video_id, videos(*)").gte("requested_at", yesterday).execute()
    if not res.data:
        await query.edit_message_text("မရှိသေးပါ။")
        return
    counts, titles = {}, {}
    for r in res.data:
        vid = r['video_id']
        counts[vid] = counts.get(vid, 0) + 1
        titles[vid] = r['videos']['title'] if r['videos'] and r['videos'].get('title') else f"Video {vid}"
    sorted_vids = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]
    msg = "🔥 *ယနေ့လူကြိုက်အများဆုံး*\n\n"
    for i, (vid, c) in enumerate(sorted_vids): msg += f"{i+1}. {titles[vid]} - ({c} views)\n"
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")]]), parse_mode="Markdown")

async def show_profile(query, user_id):
    res = supabase.table("users").select("*").eq("id", user_id).execute()
    if not res.data: return
    user = res.data[0]
    tok_res = supabase.table("tokens").select("balance").eq("user_id", user_id).execute()
    balance = tok_res.data[0]['balance'] if tok_res.data else 0
    txt = f"👤 *ပရိုဖိုင်*\nID: `{user['id']}`\nအမည်: {user['first_name']}\nအဆင့်: {user['tier'].upper()}\nဒီနေ့ကြည့်ပြီးသောအရေအတွက်: {user['daily_requests_used']}\nTokens: {balance}\nဆက်တိုက်ဝင်ရောက်မှု: {user['streak_days']} days\n"
    if user['premium_expires_at']: txt += f"Premium Exp: {user['premium_expires_at']}\n"
    await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")]]), parse_mode="Markdown")

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token: return
    app = Application.builder().token(token).build()
    app.add_handler(TypeHandler(Update, force_join_middleware), group=-1)
    app.add_handler(CommandHandler("invite", invite_link))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("set_dump_channel", set_dump_channel))
    app.add_handler(CommandHandler("set_trash_channel", set_trash_channel))
    app.add_handler(CommandHandler("set_required_channels", set_required_channels))
    app.add_handler(CommandHandler("add_ad", add_ad))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    from cron import start_background_monitors
    import threading
    t = threading.Thread(target=start_background_monitors, daemon=True)
    t.start()
    main()
