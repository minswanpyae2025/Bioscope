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

                # MLM Referral: Check if user was invited, give inviter a 10% kickback token if they buy/earn premium
                invite_res = supabase.table("invites").select("*").eq("invitee_id", user["id"]).eq("reward_given", False).execute()
                if invite_res.data:
                    inviter_id = invite_res.data[0]["inviter_id"]
                    invite_id = invite_res.data[0]["id"]
                    # Assume 10 tokens as a base "premium" cost equivalent to reward inviter with 10% (1 token)
                    # or simply 10 tokens. Let's give 5 tokens for simplicity upon getting premium
                    tok_res = supabase.table("tokens").select("balance").eq("user_id", inviter_id).execute()
                    balance = tok_res.data[0]['balance'] if tok_res.data else 0
                    supabase.table("tokens").upsert({"user_id": inviter_id, "balance": balance + 5}).execute()
                    supabase.table("invites").update({"reward_given": True}).eq("id", invite_id).execute()

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
        [InlineKeyboardButton("🎬 ရုပ်ရှင်အသစ်များ", callback_data="movies_0")],
        [InlineKeyboardButton("📺 ဇာတ်လမ်းတွဲအသစ်များ", callback_data="tvshows_0")],
        [InlineKeyboardButton("🔍 ရုပ်ရှင်ရှာရန်", callback_data="search_movies")],
        [InlineKeyboardButton("🔎 ဇာတ်လမ်းတွဲရှာရန်", callback_data="search_tv")],
        [InlineKeyboardButton("⭐ သင့်အတွက်", callback_data="for_you")],
        [InlineKeyboardButton("🔥 ယနေ့လူကြိုက်အများဆုံး", callback_data="top_24h")],
        [InlineKeyboardButton("🔖 ဆက်လက်ကြည့်ရှုရန် (Watchlist)", callback_data="watchlist_0")],
        [InlineKeyboardButton("👤 ပရိုဖိုင်", callback_data="profile")],
    ])

async def invite_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{update.effective_user.id}"
    await update.message.reply_text(f"🎁 သူငယ်ချင်းများကို ဖိတ်ခေါ်ပြီး Token ရယူပါ:\n`{link}`", parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    if db_user: await update_user_activity_and_streak(db_user)

    if context.args and context.args[0].startswith("ref_"):
        inviter_id = int(context.args[0].split("_")[1])
        if inviter_id != update.effective_user.id:
            try:
                # Add invite record, if unique violation occurs, it means already invited
                supabase.table("invites").insert({"inviter_id": inviter_id, "invitee_id": update.effective_user.id}).execute()
                tok_res = supabase.table("tokens").select("balance").eq("user_id", inviter_id).execute()
                balance = tok_res.data[0]['balance'] if tok_res.data else 0
                supabase.table("tokens").upsert({"user_id": inviter_id, "balance": balance + 5}).execute()
            except: pass

    await update.message.reply_text("🎬 *Bioscope Bot မှ ကြိုဆိုပါတယ်*\nအောက်ပါ Menu မှ ရွေးချယ်ပါ:", reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "check_joined":
        from middleware import check_force_join
        passed = await check_force_join(update, context)
        if passed:
            if query.message.photo:
                await query.message.delete()
                await query.message.reply_text("🎬 *Bioscope Bot Menu*:", reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
            else:
                await query.edit_message_text("🎬 *Bioscope Bot Menu*:", reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
        else:
            await query.answer("မဝင်ရသေးပါ", show_alert=True)
        return

    if data.startswith("movies_"): await show_movies_list(query, int(data.split("_")[1]))
    elif data.startswith("tvshows_"): await show_tvshows_list(query, int(data.split("_")[1]))
    elif data.startswith("watchlist_"): await show_watchlist(query, update.effective_user.id, int(data.split("_")[1]))
    elif data == "main_menu":
        if query.message.photo:
            await query.message.delete()
            await query.message.reply_text("🎬 *Bioscope Bot Menu*:", reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
        else:
            await query.edit_message_text("🎬 *Bioscope Bot Menu*:", reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
    elif data == "search_movies":
        context.user_data['search_type'] = 'movie'
        await query.edit_message_text("🔍 ရှာဖွေလိုသော ရုပ်ရှင်အမည်ကို ရိုက်ထည့်ပါ:")
    elif data == "search_tv":
        context.user_data['search_type'] = 'tv'
        await query.edit_message_text("🔎 ရှာဖွေလိုသော ဇာတ်လမ်းတွဲအမည်ကို ရိုက်ထည့်ပါ:")
    elif data == "profile": await show_profile(query, update.effective_user.id)
    elif data == "for_you": await handle_for_you(query, update.effective_user.id)
    elif data == "top_24h": await show_top_24h(query)
    elif data.startswith("movie_"): await handle_movie_request(query, data.split("_")[1])
    elif data.startswith("tvshow_"): await show_episodes(query, data.split("_")[1])
    elif data.startswith("episode_"): await handle_tv_request(query, data.split("_")[1], int(data.split("_")[2]))
    elif data.startswith("addwatch_"): await handle_add_watchlist(query, update.effective_user.id, data.split("_")[1], data.split("_")[2])
    elif data.startswith("sel_"): await process_tier_check_and_ad(query, update.effective_user.id, data.split("_")[1])
    elif data.startswith("rate_"): await handle_user_rating(query, update.effective_user.id, data.split("_")[1], data.split("_")[2], data.split("_")[3])
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

async def handle_user_rating(query, user_id, rating, video_type, video_post_id):
    try:
        supabase.table("user_ratings").upsert({
            "user_id": user_id,
            "video_post_id": video_post_id,
            "video_type": video_type,
            "rating": rating
        }, on_conflict="user_id, video_post_id, video_type").execute()

        await query.answer("ကျေးဇူးတင်ပါတယ်။", show_alert=True)
        # Remove the inline keyboard after rating
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception as e:
        await query.answer("❌ အမှားအယွင်းဖြစ်ပွားခဲ့သည်။", show_alert=True)

async def handle_for_you(query, user_id):
    # Get last watched video id
    res = supabase.table("users").select("last_watched_video_id, videos(*)").eq("id", user_id).execute()
    if not res.data or not res.data[0].get('last_watched_video_id') or not res.data[0].get('videos'):
        text = "❌ သင်ကြည့်ရှုခဲ့သော မှတ်တမ်းမရှိသေးပါ။"
        if query.message.photo:
            await query.message.delete()
            await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")]]))
        else:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")]]))
        return

    last_vid = res.data[0]['videos']
    if last_vid['type'] != 'movie':
        text = "❌ ဇာတ်လမ်းတွဲများအတွက် အကြံပြုချက်မရရှိနိုင်သေးပါ။ ရုပ်ရှင်ကြည့်ပြီးမှ ထပ်မံကြိုးစားပါ။"
        if query.message.photo:
            await query.message.delete()
            await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")]]))
        else:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")]]))
        return

    post_id = last_vid['post_id']
    await query.answer("🔄 စစ်ဆေးနေပါသည်...", show_alert=False)

    recommendations = await asyncio.to_thread(scraper.get_you_may_also_like, post_id)
    rec_data = recommendations.get("data", [])

    if not rec_data:
        text = "❌ အကြံပြုစရာ မရှိသေးပါ။"
        if query.message.photo:
            await query.message.delete()
            await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")]]))
        else:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")]]))
        return

    # Take first 5 recommendations
    top_recs = rec_data[:5]
    buttons = [[InlineKeyboardButton(m.get("title", "Unknown"), callback_data=f"movie_{m['id']}")] for m in top_recs]
    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")])

    text = "⭐ *သင်ဟာ ဒါကိုကြည့်ဖူးလို့ ဒါကိုလဲ ကြည့်ကြည့်ပါလား*\n\nရွေးချယ်ပါ:"
    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
    else:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def show_movies_list(query, offset):
    res = await asyncio.to_thread(scraper.browse_movies, offset)
    movies = res.get("data", [])
    if not movies:
        await query.answer("❌ နောက်ထပ်မရှိတော့ပါ။", show_alert=True)
        return
    buttons = [[InlineKeyboardButton(m.get("title", "Unknown"), callback_data=f"movie_{m['id']}")] for m in movies]

    nav_buttons = []
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"movies_{max(0, offset-30)}"))
    if len(movies) >= 30:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"movies_{offset+30}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")])
    text = "🎬 *ရုပ်ရှင်အသစ်များ* (ရွေးချယ်ပါ):"

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
    else:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def show_tvshows_list(query, offset):
    res = await asyncio.to_thread(scraper.browse_tv_shows, offset)
    shows = res.get("data", [])
    if not shows:
        await query.answer("❌ နောက်ထပ်မရှိတော့ပါ။", show_alert=True)
        return
    buttons = [[InlineKeyboardButton(s.get("title", "Unknown"), callback_data=f"tvshow_{s['id']}")] for s in shows]

    nav_buttons = []
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"tvshows_{max(0, offset-30)}"))
    if len(shows) >= 30:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"tvshows_{offset+30}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")])
    text = "📺 *ဇာတ်လမ်းတွဲအသစ်များ* (ရွေးချယ်ပါ):"

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
    else:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def handle_add_watchlist(query, user_id, video_type, video_post_id):
    try:
        supabase.table("watchlist").insert({"user_id": user_id, "video_post_id": video_post_id, "video_type": video_type}).execute()
        await query.answer("✅ Watchlist တွင် သိမ်းဆည်းပြီးပါပြီ။", show_alert=True)
    except Exception as e:
        if 'duplicate' in str(e).lower() or 'unique' in str(e).lower():
            await query.answer("ℹ️ သင့် Watchlist တွင် ရှိပြီးသားဖြစ်ပါသည်။", show_alert=True)
        else:
            await query.answer("❌ Error adding to watchlist.", show_alert=True)

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

async def show_watchlist(query, user_id, offset):
    res = supabase.table("watchlist").select("*").eq("user_id", user_id).order("added_at", desc=True).range(offset, offset+29).execute()
    items = res.data
    if not items:
        if offset == 0:
            msg = "❌ သင့် Watchlist တွင် ဘာမှမရှိသေးပါ။"
            if query.message.photo:
                await query.message.delete()
                await query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")]]))
            else:
                await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")]]))
        else:
            await query.answer("❌ နောက်ထပ်မရှိတော့ပါ။", show_alert=True)
        return

    buttons = []
    for item in items:
        title_prefix = "🎬" if item['video_type'] == 'movie' else "📺"
        callback = f"movie_{item['video_post_id']}" if item['video_type'] == 'movie' else f"tvshow_{item['video_post_id']}"
        buttons.append([InlineKeyboardButton(f"{title_prefix} {item['video_post_id']}", callback_data=callback)])

    nav_buttons = []
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"watchlist_{max(0, offset-30)}"))
    if len(items) >= 30:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"watchlist_{offset+30}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")])

    text = "🔖 *Watchlist*:"
    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
    else:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def show_episodes(query, tv_id):
    episodes = await asyncio.to_thread(scraper.get_tv_episodes, tv_id)
    if not episodes:
        await query.answer("❌ မတွေ့ရှိပါ။", show_alert=True)
        return

    tv_details = await asyncio.to_thread(scraper.get_tv_show_details, tv_id)
    poster_url = tv_details.get("data", {}).get("poster")

    buttons = [[InlineKeyboardButton(f"Episode {ep.get('episode_number', '?')} – {ep.get('title', 'Unknown')}", callback_data=f"episode_{tv_id}_{idx}")] for idx, ep in enumerate(episodes)]
    buttons.append([InlineKeyboardButton("🔖 Save to Watchlist", callback_data=f"addwatch_tv_{tv_id}")])
    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="tvshows_0")])

    text = "📺 အပိုင်းရွေးချယ်ပါ:"

    if poster_url:
        try:
            await query.message.delete()
        except:
            pass
        await query.message.reply_photo(photo=poster_url, caption=text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
    else:
        try:
            await query.message.delete()
        except:
            pass
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def handle_movie_request(query, movie_id):
    if not query.message.photo:
        await query.edit_message_text("🔄 စစ်ဆေးနေပါသည်...")

    # We need the movie details to get the title
    movie_details = await asyncio.to_thread(scraper.get_movie_details, movie_id)
    movie_title = movie_details.get("data", {}).get("title", f"Movie {movie_id}")
    poster_url = movie_details.get("data", {}).get("poster")

    streams = await asyncio.to_thread(scraper.get_movie_streams, movie_id)
    if not streams:
        await query.answer("❌ မတွေ့ရှိပါ။", show_alert=True)
        return
    buttons = []
    for idx, s in enumerate(streams):
        res = s.get('resolution', 'Unknown')
        size = s.get('size', 'Unknown')
        cache_id = str(uuid.uuid4())[:8]

        # Store title in cache
        full_title = f"🎬 {movie_title} ({res})"
        STREAM_CACHE[cache_id] = {"stream": s, "post_id": movie_id, "is_movie": True, "title": full_title}

        buttons.append([InlineKeyboardButton(f"🎬 {res} | 📦 {size}", callback_data=f"sel_{cache_id}")])

    buttons.append([InlineKeyboardButton("🔖 Save to Watchlist", callback_data=f"addwatch_movie_{movie_id}")])
    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="movies_0")])

    text = f"🎬 **{movie_title}**\nအရည်အသွေး ရွေးချယ်ပါ:"

    if poster_url:
        try:
            await query.message.delete()
        except:
            pass
        await query.message.reply_photo(photo=poster_url, caption=text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
    else:
        try:
            await query.message.delete()
        except:
            pass
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def handle_tv_request(query, tv_id, ep_idx):
    if not query.message.photo:
        await query.edit_message_text("🔄 စစ်ဆေးနေပါသည်...")

    # We need the show title
    tv_details = await asyncio.to_thread(scraper.get_tv_show_details, tv_id)
    tv_title = tv_details.get("data", {}).get("title", f"TV Show {tv_id}")

    tv_details = await asyncio.to_thread(scraper.get_tv_show_details, tv_id)
    tv_title = tv_details.get("data", {}).get("title", f"TV Show {tv_id}")
    poster_url = tv_details.get("data", {}).get("poster")

    episodes = await asyncio.to_thread(scraper.get_tv_episodes, tv_id)
    if not episodes or ep_idx >= len(episodes):
        await query.answer("❌ မတွေ့ရှိပါ။", show_alert=True)
        return

    target_ep = episodes[ep_idx]
    target_ep_id = target_ep.get("id")
    ep_num = target_ep.get("episode_number", "?")
    ep_name = target_ep.get("title", "")

    streams = await asyncio.to_thread(scraper.get_tv_streams, target_ep_id)
    if not streams:
        await query.answer("❌ မတွေ့ရှိပါ။", show_alert=True)
        return
    buttons = []
    for idx, s in enumerate(streams):
        res = s.get('resolution', 'Unknown')
        size = s.get('size', 'Unknown')
        cache_id = str(uuid.uuid4())[:8]

        # Store title in cache
        full_title = f"📺 {tv_title} - Episode {ep_num} {ep_name} ({res})"
        STREAM_CACHE[cache_id] = {"stream": s, "post_id": target_ep_id, "is_movie": False, "tv_id": tv_id, "title": full_title}

        buttons.append([InlineKeyboardButton(f"📺 {res} | 📦 {size}", callback_data=f"sel_{cache_id}")])

    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data=f"tvshow_{tv_id}")])
    text = f"📺 **{tv_title} (Ep {ep_num})**\nအရည်အသွေး ရွေးချယ်ပါ:"

    if poster_url:
        try:
            await query.message.delete()
        except:
            pass
        await query.message.reply_photo(photo=poster_url, caption=text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
    else:
        try:
            await query.message.delete()
        except:
            pass
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

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
         await query.answer("❌ ယနေ့အတွက် သတ်မှတ်ထားသော အရေအတွက် ပြည့်သွားပါပြီ။", show_alert=True)
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

    # Update last watched
    internal_id = v_res.data[0]['id'] if v_res.data else None
    if not internal_id:
        ins = supabase.table("videos").insert({"post_id": post_id, "type": v_type, "resolution": resolution, "title": display_title}).execute()
        internal_id = ins.data[0]['id']

    supabase.table("users").update({"last_watched_video_id": internal_id}).eq("id", user_id).execute()

    if v_res.data and v_res.data[0].get("is_alive") and v_res.data[0].get("telegram_file_id"):
        dump_channel = get_admin_config("dump_channel_id")
        msg_id = v_res.data[0]["dump_message_id"]
        saved_title = v_res.data[0].get("title", display_title)
        try:
            rating_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("👍 Like", callback_data=f"rate_like_{v_type}_{post_id}"), InlineKeyboardButton("👎 Dislike", callback_data=f"rate_dislike_{v_type}_{post_id}")]
            ])
            await query.bot.copy_message(chat_id=user_id, from_chat_id=dump_channel, message_id=msg_id, caption=f"**{saved_title}**\n\n@BioscopeBot", parse_mode="Markdown", reply_markup=rating_kb, protect_content=True)

            if query.message.photo:
                await query.message.delete()
            else:
                await query.edit_message_text("✅ ပို့ဆောင်ပြီးပါပြီ။")
                await asyncio.sleep(3)
                await query.message.delete()
            return
        except Exception as e:
            logger.error(f"Copy message failed: {e}")
            supabase.table("videos").update({"is_alive": False}).eq("id", internal_id).execute()

    if query.message.photo:
        await query.message.delete()
        msg = await query.message.reply_text("📥 ဒေါင်းလုဒ်စတင်နေပါပြီ...")
    else:
        msg = query.message
        await query.edit_message_text("📥 ဒေါင်းလုဒ်စတင်နေပါပြီ...")
    url = await asyncio.to_thread(scraper.extract_stream_url, target_stream, post_id, is_movie)

    if not url:
        await query.edit_message_text("❌ Error getting stream.")
        return

    internal_id = v_res.data[0]['id'] if v_res.data else None
    if not internal_id:
        ins = supabase.table("videos").insert({"post_id": post_id, "type": v_type, "resolution": resolution, "title": display_title}).execute()
        internal_id = ins.data[0]['id']

    req_ins = supabase.table("user_requests").insert({"user_id": user_id, "video_id": internal_id, "status": "queued"}).execute()
    req_id = req_ins.data[0]['id']

    res = supabase.table("users").select("tier").eq("id", user_id).execute()
    tier = res.data[0]['tier'] if res.data else "free"

    if redis_client:
        queue_name = "vip_queue" if tier == "premium" else "leech_queue"
        q_len = redis_client.llen(queue_name)
        est_mins = 2 + (q_len * 2)
        payload = {"internal_video_id": internal_id, "url": url, "req_id": req_id, "user_id": user_id, "tier": tier}
        redis_client.lpush(queue_name, json.dumps(payload))

    try:
        await msg.edit_text(f"📥 တန်းစီထားပါသည်။ ခန့်မှန်းစောင့်ဆိုင်းချိန်: ~{est_mins} မိနစ်")
    except:
        pass

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

async def redis_event_listener(app):
    if not redis_client:
        return
    pubsub = redis_client.pubsub()
    pubsub.subscribe("wzmlx_events")
    logger.info("Listening for wzmlx_events on Redis...")

    while True:
        try:
            message = await asyncio.to_thread(pubsub.get_message, ignore_subscribe_messages=True, timeout=1.0)
            if message:
                data = json.loads(message['data'])
                event = data.get("event")
                internal_video_id = data.get("internal_video_id")
                req_id = data.get("req_id")

                if event == "upload_complete":
                    file_id = data.get("telegram_file_id")
                    dump_message_id = data.get("dump_message_id")

                    supabase.table("videos").update({
                        "telegram_file_id": file_id,
                        "dump_message_id": dump_message_id,
                        "is_alive": True
                    }).eq("id", internal_video_id).execute()

                    supabase.table("user_requests").update({"status": "uploaded"}).eq("id", req_id).execute()

                    # Notify user if they were waiting?
                    # The message is sent by the worker bot directly to the dump channel.
                    # Actually, the user doesn't get it until they request again, or we forward it.
                    # In process_video_request, we told them "queueing".
                    # Let's forward it to the user now.
                    req_res = supabase.table("user_requests").select("user_id").eq("id", req_id).execute()
                    if req_res.data:
                        user_id = req_res.data[0]['user_id']
                        vid_res = supabase.table("videos").select("*").eq("id", internal_video_id).execute()
                        if vid_res.data:
                            dump_channel = get_admin_config("dump_channel_id")
                            msg_id = vid_res.data[0]["dump_message_id"]
                            v_type = vid_res.data[0]["type"]
                            post_id = vid_res.data[0]["post_id"]
                            saved_title = vid_res.data[0].get("title", "Bioscope Video")

                            try:
                                rating_kb = InlineKeyboardMarkup([
                                    [InlineKeyboardButton("👍 Like", callback_data=f"rate_like_{v_type}_{post_id}"), InlineKeyboardButton("👎 Dislike", callback_data=f"rate_dislike_{v_type}_{post_id}")]
                                ])
                                await app.bot.copy_message(chat_id=user_id, from_chat_id=dump_channel, message_id=msg_id, caption=f"**{saved_title}**\n\n@BioscopeBot", parse_mode="Markdown", reply_markup=rating_kb, protect_content=True)
                            except Exception as e:
                                logger.error(f"Failed to copy message to user {user_id}: {e}")

                elif event == "upload_failed":
                    supabase.table("user_requests").update({"status": "failed"}).eq("id", req_id).execute()

                    # Auto-Resolution Fallback
                    req_res = supabase.table("user_requests").select("user_id").eq("id", req_id).execute()
                    if req_res.data:
                        user_id = req_res.data[0]['user_id']
                        vid_res = supabase.table("videos").select("*").eq("id", internal_video_id).execute()
                        if vid_res.data:
                            v_type = vid_res.data[0]["type"]
                            post_id = vid_res.data[0]["post_id"]
                            failed_res = vid_res.data[0]["resolution"]
                            fallback_res = "720p" if failed_res == "1080p" else "480p" if failed_res == "720p" else None

                            try:
                                if fallback_res:
                                    # Create a dummy cache ID to restart the request loop
                                    cache_id = str(uuid.uuid4())[:8]
                                    # Re-fetch streams
                                    is_movie = (v_type == "movie")
                                    streams = await asyncio.to_thread(scraper.get_movie_streams if is_movie else scraper.get_tv_streams, post_id)
                                    target_stream = next((s for s in streams if s.get('resolution') == fallback_res), None)

                                    if target_stream:
                                        STREAM_CACHE[cache_id] = {"stream": target_stream, "post_id": post_id, "is_movie": is_movie, "title": f"{vid_res.data[0]['title']} ({fallback_res})"}
                                        buttons = [[InlineKeyboardButton(f"✅ ဟုတ်ကဲ့၊ {fallback_res} ကိုကြည့်ပါမည်", callback_data=f"sel_{cache_id}")]]
                                        await app.bot.send_message(chat_id=user_id, text=f"❌ {failed_res} သည် ချို့ယွင်းနေပါသည်။ {fallback_res} ဖြင့် ကြည့်ရှုလိုပါသလား?", reply_markup=InlineKeyboardMarkup(buttons))
                                    else:
                                        await app.bot.send_message(chat_id=user_id, text=f"❌ {failed_res} သည် ချို့ယွင်းနေပါသည်။ တောင်းပန်ပါသည်။")
                                else:
                                    await app.bot.send_message(chat_id=user_id, text=f"❌ သင့်ဗီဒီယိုကို ရယူရာတွင် ချို့ယွင်းမှုဖြစ်ပေါ်ခဲ့ပါသည်။")
                            except Exception as e:
                                logger.error(f"Failed to notify user {user_id} of failure: {e}")

        except Exception as e:
            logger.error(f"Redis pub/sub error: {e}")
            await asyncio.sleep(5)
        await asyncio.sleep(0.1)

async def post_init(app: Application):
    asyncio.create_task(redis_event_listener(app))

if __name__ == "__main__":
    from cron import start_background_monitors
    import threading
    t = threading.Thread(target=start_background_monitors, daemon=True)
    t.start()

    token = os.environ.get("BOT_TOKEN")
    if token:
        app = Application.builder().token(token).post_init(post_init).build()

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
