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
    from telegram import WebAppInfo
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 ရုပ်ရှင်အသစ်များ", callback_data="movies_0")],
        [InlineKeyboardButton("📺 ဇာတ်လမ်းတွဲအသစ်များ", callback_data="tvshows_0")],
        [InlineKeyboardButton("🔍 ရုပ်ရှင်ရှာရန်", callback_data="search_movies")],
        [InlineKeyboardButton("🔎 ဇာတ်လမ်းတွဲရှာရန်", callback_data="search_tv")],
        [InlineKeyboardButton("📋 Watchlist", callback_data="watchlist")],
        [InlineKeyboardButton("▶️ Continue Watching", callback_data="continue_watching")],
        [InlineKeyboardButton("⭐ သင့်အတွက်", callback_data="for_you")],
        [InlineKeyboardButton("🔥 ယနေ့လူကြိုက်အများဆုံး", callback_data="top_24h")],
        [InlineKeyboardButton("📱 Mini App", web_app=WebAppInfo(url="https://bioscopetelegram.onrender.com/app/miniapp"))],
        [InlineKeyboardButton("👤 ပရိုဖိုင်", callback_data="profile")],
    ])

def dummy_replace():
    pass

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

    if data.startswith("movies_"): await show_movies_list(query, int(data.split("_")[1]))
    elif data.startswith("tvshows_"): await show_tvshows_list(query, int(data.split("_")[1]))
    elif data == "watchlist": await show_watchlist(query, update.effective_user.id)
    elif data == "continue_watching": await show_continue_watching(query, update.effective_user.id)
    elif data.startswith("add_watchlist_"): await add_to_watchlist(query, update.effective_user.id, data)
    elif data.startswith("review_"): await handle_review(query, update.effective_user.id, data)
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
    elif data == "buy_premium": await handle_buy_premium(query, update.effective_user.id)
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

async def show_movies_list(query, offset=0):
    res = await asyncio.to_thread(scraper.browse_movies, offset)
    movies = res.get("data", [])[:30]
    if not movies and offset == 0:
        await query.edit_message_text("❌ မတွေ့ရှိပါ။")
        return
    buttons = [[InlineKeyboardButton(m.get("title", "Unknown"), callback_data=f"movie_{m['id']}")] for m in movies]

    nav_buttons = []
    if offset >= 30:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"movies_{offset-30}"))
    if len(movies) == 30:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"movies_{offset+30}"))
    if nav_buttons: buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")])
    await query.edit_message_text("🎬 *ရုပ်ရှင်အသစ်များ* (ရွေးချယ်ပါ):", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def show_tvshows_list(query, offset=0):
    res = await asyncio.to_thread(scraper.browse_tv_shows, offset)
    shows = res.get("data", [])[:30]
    if not shows and offset == 0:
        await query.edit_message_text("❌ မတွေ့ရှိပါ။")
        return
    buttons = [[InlineKeyboardButton(s.get("title", "Unknown"), callback_data=f"tvshow_{s['id']}")] for s in shows]

    nav_buttons = []
    if offset >= 30:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"tvshows_{offset-30}"))
    if len(shows) == 30:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"tvshows_{offset+30}"))
    if nav_buttons: buttons.append(nav_buttons)

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
    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="tvshows_0")])
    await query.edit_message_text("📺 အပိုင်းရွေးချယ်ပါ:", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def handle_movie_request(query, movie_id):
    await query.edit_message_text("🔄 စစ်ဆေးနေပါသည်...")

    # We need the movie details to get the title
    movie_details = await asyncio.to_thread(scraper.get_movie_details, movie_id)
    movie_title = movie_details.get("data", {}).get("title", f"Movie {movie_id}")

    streams = await asyncio.to_thread(scraper.get_movie_streams, movie_id)
    if not streams:
        await query.edit_message_text("❌ မတွေ့ရှိပါ။")
        return
    buttons = []
    for idx, s in enumerate(streams):
        res = s.get('resolution', 'Unknown')
        size = s.get('size', 'Unknown')
        cache_id = str(uuid.uuid4())[:8]

        # Store title in cache
        full_title = f"🎬 {movie_title} ({res})"
        STREAM_CACHE[cache_id] = {"stream": s, "post_id": movie_id, "is_movie": True, "title": full_title}

        buttons.append([InlineKeyboardButton(f"🎬 {res} | {size} (Option {idx+1})", callback_data=f"sel_{cache_id}")])
    buttons.append([InlineKeyboardButton("📋 Save to Watchlist", callback_data=f"add_watchlist_movie_{movie_id}")])
    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="movies_0")])
    await query.edit_message_text(f"🎬 **{movie_title}**\nအရည်အသွေး ရွေးချယ်ပါ:", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def handle_tv_request(query, tv_id, ep_idx):
    await query.edit_message_text("🔄 စစ်ဆေးနေပါသည်...")

    # We need the show title
    tv_details = await asyncio.to_thread(scraper.get_tv_show_details, tv_id)
    tv_title = tv_details.get("data", {}).get("title", f"TV Show {tv_id}")

    episodes = await asyncio.to_thread(scraper.get_tv_episodes, tv_id)
    if not episodes or ep_idx >= len(episodes):
        await query.edit_message_text("❌ မတွေ့ရှိပါ။")
        return

    target_ep = episodes[ep_idx]
    target_ep_id = target_ep.get("id")
    ep_num = target_ep.get("episode_number", "?")
    ep_name = target_ep.get("title", "")

    streams = await asyncio.to_thread(scraper.get_tv_streams, target_ep_id)
    if not streams:
        await query.edit_message_text("❌ မတွေ့ရှိပါ။")
        return
    buttons = []
    for idx, s in enumerate(streams):
        res = s.get('resolution', 'Unknown')
        size = s.get('size', 'Unknown')
        cache_id = str(uuid.uuid4())[:8]

        # Store title in cache
        full_title = f"📺 {tv_title} - Episode {ep_num} {ep_name} ({res})"
        STREAM_CACHE[cache_id] = {"stream": s, "post_id": target_ep_id, "is_movie": False, "tv_id": tv_id, "title": full_title}

        buttons.append([InlineKeyboardButton(f"📺 {res} | {size} (Option {idx+1})", callback_data=f"sel_{cache_id}")])
    buttons.append([InlineKeyboardButton("📋 Save to Watchlist", callback_data=f"add_watchlist_tv_{tv_id}")])
    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data=f"tvshow_{tv_id}")])
    await query.edit_message_text(f"📺 **{tv_title} (Ep {ep_num})**\nအရည်အသွေး ရွေးချယ်ပါ:", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

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

    post_id = str(s_data["post_id"])
    is_movie = s_data["is_movie"]
    display_title = s_data.get("title", "Bioscope Video")
    resolution = target_stream.get('resolution', 'Unknown')
    v_type = "movie" if is_movie else "tv_episode"

    v_res = supabase.table("videos").select("*").eq("post_id", post_id).eq("type", v_type).eq("resolution", resolution).execute()

    if v_res.data and v_res.data[0].get("is_alive") and v_res.data[0].get("telegram_file_id"):
        dump_channel = get_admin_config("dump_channel_id")
        msg_id = v_res.data[0]["dump_message_id"]
        saved_title = v_res.data[0].get("title", display_title)
        try:
            await query.bot.copy_message(chat_id=user_id, from_chat_id=dump_channel, message_id=msg_id, caption=f"**{saved_title}**\n\n@BioscopeBot", parse_mode="Markdown", protect_content=True)
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
        # Auto-Resolution Fallback
        res_list = ['1080p', '720p', '480p', '360p']
        if resolution in res_list:
            res_list.remove(resolution)

        streams = []
        if is_movie:
            streams = await asyncio.to_thread(scraper.get_movie_streams, post_id)
        else:
            streams = await asyncio.to_thread(scraper.get_tv_streams, post_id)

        fallback_stream = None
        for r in res_list:
            for s in streams:
                if s.get('resolution') == r:
                    fallback_stream = s
                    break
            if fallback_stream: break

        if fallback_stream:
            new_res = fallback_stream.get('resolution')
            new_cache_id = str(uuid.uuid4())[:8]
            STREAM_CACHE[new_cache_id] = {"stream": fallback_stream, "post_id": post_id, "is_movie": is_movie, "title": data.get('title', 'Bioscope Video')}

            buttons = [
                [InlineKeyboardButton(f"✅ Yes, give me {new_res}", callback_data=f"sel_{new_cache_id}")],
                [InlineKeyboardButton("🔙 No, go back", callback_data="main_menu")]
            ]
            await query.edit_message_text(f"❌ {resolution} is dead.\nWould you like {new_res} instead?", reply_markup=InlineKeyboardMarkup(buttons))
            return

        await query.edit_message_text("❌ Error getting stream. All resolutions might be dead.")
        return

    internal_id = v_res.data[0]['id'] if v_res.data else None
    if not internal_id:
        ins = supabase.table("videos").insert({"post_id": post_id, "type": v_type, "resolution": resolution, "title": display_title}).execute()
        internal_id = ins.data[0]['id']

    req_ins = supabase.table("user_requests").insert({"user_id": user_id, "video_id": internal_id, "status": "queued"}).execute()
    req_id = req_ins.data[0]['id']

    if redis_client:
        q_len = redis_client.llen("leech_queue")
        est_mins = 2 + (q_len * 2)
        payload = {"internal_video_id": internal_id, "url": url, "req_id": req_id}

        # Check tier for queue priority
        res_user = supabase.table("users").select("tier").eq("id", user_id).execute()
        tier = res_user.data[0]['tier'] if res_user.data else "free"

        if tier == 'premium':
            redis_client.lpush("vip_queue", json.dumps(payload))
            est_mins = 0 # VIP gets instant
        else:
            redis_client.lpush("leech_queue", json.dumps(payload))

    await query.edit_message_text(f"📥 တန်းစီထားပါသည်။ ခန့်မှန်းစောင့်ဆိုင်းချိန်: ~{est_mins} မိနစ်")

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
    buttons = []
    if user['tier'] != 'premium':
        buttons.append([InlineKeyboardButton("💎 Buy Premium (100 Tokens)", callback_data="buy_premium")])
    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")])
    await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

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
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    from cron import start_background_monitors
    import threading
    t = threading.Thread(target=start_background_monitors, daemon=True)
    t.start()
    main()

async def handle_buy_premium(query, user_id):
    res = supabase.table("users").select("*").eq("id", user_id).execute()
    if not res.data: return
    user = res.data[0]
    if user['tier'] == 'premium':
        await query.answer("You are already premium!", show_alert=True)
        return
    tok_res = supabase.table("tokens").select("balance").eq("user_id", user_id).execute()
    balance = tok_res.data[0]['balance'] if tok_res.data else 0
    if balance < 100:
        await query.answer("Not enough tokens! You need 100.", show_alert=True)
        return

    # Deduct 100 tokens, grant premium
    supabase.table("tokens").update({"balance": balance - 100}).eq("user_id", user_id).execute()
    new_expires = datetime.now(TZ) + timedelta(days=30)
    supabase.table("users").update({"tier": "premium", "premium_expires_at": new_expires.isoformat()}).eq("id", user_id).execute()

    # Referral kickback
    inv_res = supabase.table("invites").select("inviter_id").eq("invitee_id", user_id).execute()
    if inv_res.data:
        inviter_id = inv_res.data[0]['inviter_id']
        inviter_tok_res = supabase.table("tokens").select("balance").eq("user_id", inviter_id).execute()
        inviter_bal = inviter_tok_res.data[0]['balance'] if inviter_tok_res.data else 0
        supabase.table("tokens").upsert({"user_id": inviter_id, "balance": inviter_bal + 10}).execute()
        try:
            await query.bot.send_message(chat_id=inviter_id, text=f"🎉 သင်ဖိတ်ခေါ်ထားသောသူတစ်ဦး Premium ဝယ်ယူလိုက်သောကြောင့် သင့်အား 10 Tokens ဆုချီးမြှင့်လိုက်ပါသည်။")
        except: pass

    await query.answer("Success! You are now Premium.", show_alert=True)
    await show_profile(query, user_id)

async def show_watchlist(query, user_id):
    res = supabase.table("watchlists").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(20).execute()
    if not res.data:
        await query.edit_message_text("❌ Watchlist တွင် မရှိသေးပါ။", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")]]))
        return
    buttons = []
    for item in res.data:
        cb = f"movie_{item['post_id']}" if item['is_movie'] else f"tvshow_{item['post_id']}"
        buttons.append([InlineKeyboardButton(item['title'], callback_data=cb)])
    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")])
    await query.edit_message_text("📋 *Watchlist*:", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def show_continue_watching(query, user_id):
    res = supabase.table("user_requests").select("*, videos(*)").eq("user_id", user_id).in_("status", ["uploaded", "completed"]).order("requested_at", desc=True).limit(10).execute()
    if not res.data:
        await query.edit_message_text("❌ မှတ်တမ်း မရှိသေးပါ။", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")]]))
        return
    buttons = []
    seen = set()
    for req in res.data:
        vid = req.get("videos")
        if not vid: continue
        title = vid.get('title', 'Unknown')
        post_id = vid.get('post_id')
        if post_id in seen: continue
        seen.add(post_id)
        cb = f"movie_{post_id}" if vid['type'] == 'movie' else f"tvshow_{post_id}"
        buttons.append([InlineKeyboardButton(title, callback_data=cb)])
    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")])
    await query.edit_message_text("▶️ *Continue Watching*:", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def add_to_watchlist(query, user_id, data):
    parts = data.split("_")
    v_type = parts[2]
    post_id = parts[3]
    is_movie = (v_type == "movie")

    # We need the title
    title = f"Item {post_id}"
    if is_movie:
        movie_details = await asyncio.to_thread(scraper.get_movie_details, post_id)
        title = movie_details.get("data", {}).get("title", title)
    else:
        tv_details = await asyncio.to_thread(scraper.get_tv_show_details, post_id)
        title = tv_details.get("data", {}).get("title", title)

    try:
        supabase.table("watchlists").insert({
            "user_id": user_id,
            "post_id": post_id,
            "is_movie": is_movie,
            "title": title
        }).execute()
        await query.answer("✅ Watchlist သို့ ထည့်သွင်းပြီးပါပြီ။", show_alert=True)
    except Exception as e:
        await query.answer("Watchlist တွင် ရှိပြီးသားဖြစ်ပါသည်။", show_alert=True)


async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.effective_message.web_app_data.data
    # Convert it to a mock query object so we can use existing handlers
    class MockQuery:
        def __init__(self, data, message, bot):
            self.data = data
            self.message = message
            self.bot = bot
        async def edit_message_text(self, *args, **kwargs):
            return await self.message.reply_text(*args, **kwargs)
        async def answer(self, *args, **kwargs):
            pass

    query = MockQuery(data, update.effective_message, context.bot)
    if data.startswith("movie_"): await handle_movie_request(query, data.split("_")[1])
    elif data.startswith("tvshow_"): await show_episodes(query, data.split("_")[1])

async def handle_review(query, user_id, data):
    parts = data.split("_")
    rating = parts[1] # 'like' or 'dislike'
    video_id = int(parts[2])

    try:
        supabase.table("user_reviews").upsert({
            "user_id": user_id,
            "video_id": video_id,
            "rating": rating
        }, on_conflict="user_id,video_id").execute()
        await query.answer("ကျေးဇူးတင်ပါသည်။", show_alert=True)
        await query.message.edit_reply_markup(reply_markup=None)
    except:
        pass
