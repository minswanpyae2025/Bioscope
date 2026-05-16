import sys
import logging
import requests
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ConversationHandler, ContextTypes
)

from finalworking import BioscopeInteractiveScraper

# -------------------------------------------------------------------
# Setup logging
# -------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Create scraper instance
# -------------------------------------------------------------------
scraper = BioscopeInteractiveScraper(
    email="kt20202004@gmail.com",
    password="#Zawzaw123"
)
if not scraper.login():
    print("Login failed! Exiting.")
    sys.exit(1)

# -------------------------------------------------------------------
# Helper functions (same as your working script)
# -------------------------------------------------------------------
def get_movie_direct_url(movie_id: str) -> Optional[str]:
    data = scraper.get_movie_details(movie_id)
    movie_data = data.get("data", {})
    streams = movie_data.get("movie_streaming_links") or movie_data.get("streaming_links", [])
    if not streams:
        return None
    target = streams[0]
    payload = {
        "id": str(target['id']),
        "type": target.get('type', 'streaming'),
        "server_name": target.get('server_name'),
        "device_id": scraper.device_id,
        "uuid": scraper.device_id,
        "member_id": scraper.member_id
    }
    link_res = scraper._post("movie/link", "movie_link", payload)
    enc_url = link_res.get("data")
    if not enc_url and "url" in target and len(target["url"]) > 20:
        enc_url = target["url"]
    if enc_url:
        clean_url = scraper.decrypt_aes_url(enc_url)
        scraper._post("watch/movies", "watch_movie", {
            "post_id": movie_id, "post_type": "movies",
            "member_id": scraper.member_id, "uuid": scraper.device_id
        })
        return clean_url
    return None

def get_tv_episode_direct_url(tv_id: str, episode_index: int) -> Optional[str]:
    tv_details = scraper.get_tv_show_details(tv_id)
    raw_data = tv_details.get("data", {})
    if not raw_data:
        return None

    episodes = []
    if "seasons" in raw_data:
        for season in raw_data["seasons"]:
            for ep in season.get("episodes", []):
                episodes.append(ep)
    elif "episodes" in raw_data:
        episodes = raw_data["episodes"]
    elif isinstance(raw_data, list):
        episodes = raw_data

    if not episodes or episode_index >= len(episodes):
        return None

    target_ep = episodes[episode_index]
    target_ep_id = target_ep.get("id")
    if not target_ep_id:
        return None

    streams = (target_ep.get("tvshow_streaming_links") or
               target_ep.get("tv_show_episode_streaming_links") or
               target_ep.get("episode_streaming_links") or
               target_ep.get("streaming_links") or
               target_ep.get("links") or [])
    if not streams:
        link_data = scraper._get(f"tv-shows/episodes/{target_ep_id}", "tv_episodes")
        raw_links = link_data.get("data", [])
        if isinstance(raw_links, list):
            streams = raw_links
        elif isinstance(raw_links, dict):
            streams = (raw_links.get("tvshow_streaming_links") or
                       raw_links.get("streaming_links") or [])
            if not streams and "server_name" in raw_links:
                streams = [raw_links]

    if not streams:
        return None

    streaming_links = [s for s in streams if s.get("type") == "streaming"]
    target_stream = streaming_links[0] if streaming_links else streams[0]

    payload = {
        "id": str(target_stream.get('id', '')),
        "type": target_stream.get('type', 'streaming'),
        "server_name": target_stream.get('server_name', ''),
        "device_id": scraper.device_id,
        "uuid": scraper.device_id,
        "member_id": scraper.member_id
    }
    link_res = scraper._post("tv-shows/episode/link", "tv_link", payload)
    enc_url = link_res.get("data")
    if not enc_url and "url" in target_stream and len(target_stream["url"]) > 20:
        enc_url = target_stream["url"]
    if enc_url:
        clean_url = scraper.decrypt_aes_url(enc_url)
        scraper._post("watch/tv-shows", "watch_tv", {
            "post_id": target_ep_id, "post_type": "tv-shows",
            "member_id": scraper.member_id, "uuid": scraper.device_id
        })
        return clean_url
    return None

# -------------------------------------------------------------------
# Bot Handlers
# -------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("🎬 Latest Movies", callback_data="movies")],
        [InlineKeyboardButton("📺 Latest TV Shows", callback_data="tvshows")],
        [InlineKeyboardButton("🔍 Search Movies", callback_data="search_movies")],
        [InlineKeyboardButton("🔎 Search TV Shows", callback_data="search_tv")],
        [InlineKeyboardButton("👤 Profile", callback_data="profile")],
        [InlineKeyboardButton("💎 Subscription", callback_data="subscription")],
    ]
    await update.message.reply_text(
        "🎬 *Bioscope Bot*\nChoose an option:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    logger.info(f"Button pressed: {data}")

    if data == "movies":
        await show_movies_list(query)
    elif data == "tvshows":
        await show_tvshows_list(query)
    elif data == "profile":
        await show_profile(query)
    elif data == "subscription":
        await show_subscription(query)
    elif data.startswith("movie_"):
        movie_id = data.split("_")[1]
        await extract_movie(query, movie_id)
    elif data.startswith("tvshow_"):
        tv_id = data.split("_")[1]
        await show_episodes(query, tv_id)
    elif data.startswith("episode_"):
        _, tv_id, ep_idx = data.split("_")
        await extract_tv_episode(query, tv_id, int(ep_idx))
    elif data == "main_menu":
        await main_menu(update, context)
    elif data == "search_movies":
        await search_movies_start(update, context)
    elif data == "search_tv":
        await search_tv_start(update, context)

async def show_movies_list(query):
    res = scraper.browse_movies()
    movies = res.get("data", [])[:30]
    if not movies:
        await query.edit_message_text("No movies found.")
        return
    buttons = [[InlineKeyboardButton(m.get("title", "Unknown"), callback_data=f"movie_{m['id']}")] for m in movies]
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
    await query.edit_message_text("🎬 *Latest Movies* – Select a movie:", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def show_tvshows_list(query):
    res = scraper.browse_tv_shows()
    shows = res.get("data", [])[:30]
    if not shows:
        await query.edit_message_text("No TV shows found.")
        return
    buttons = [[InlineKeyboardButton(s.get("title", "Unknown"), callback_data=f"tvshow_{s['id']}")] for s in shows]
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
    await query.edit_message_text("📺 *Latest TV Shows* – Select a show:", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def show_episodes(query, tv_id: str):
    tv_details = scraper.get_tv_show_details(tv_id)
    raw_data = tv_details.get("data", {})
    if not raw_data:
        await query.edit_message_text("Failed to load TV show details.")
        return

    episodes = []
    if "seasons" in raw_data:
        for season in raw_data["seasons"]:
            sn = season.get("season_number", "?")
            for ep in season.get("episodes", []):
                ep_num = ep.get("episode_number") or "?"
                title = ep.get("title") or "Unknown"
                episodes.append((ep, f"S{sn}E{ep_num} – {title}"))
    elif "episodes" in raw_data:
        for ep in raw_data["episodes"]:
            ep_num = ep.get("episode_number") or "?"
            title = ep.get("title") or "Unknown"
            episodes.append((ep, f"Episode {ep_num} – {title}"))

    if not episodes:
        await query.edit_message_text("No episodes found.")
        return

    buttons = []
    for idx, (_, display) in enumerate(episodes):
        buttons.append([InlineKeyboardButton(display, callback_data=f"episode_{tv_id}_{idx}")])
    buttons.append([InlineKeyboardButton("🔙 Back to TV Shows", callback_data="tvshows")])
    await query.edit_message_text(f"📺 *{raw_data.get('title', 'TV Show')}* – Choose episode:", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def extract_movie(query, movie_id: str):
    await query.edit_message_text(f"⏳ Fetching link for movie {movie_id}...")
    url = get_movie_direct_url(movie_id)
    if url:
        await query.edit_message_text(f"🎬 *Movie link:*\n`{url}`", parse_mode="Markdown")
    else:
        await query.edit_message_text("❌ Failed to extract movie link.")

async def extract_tv_episode(query, tv_id: str, episode_idx: int):
    await query.edit_message_text("⏳ Fetching episode link...")
    url = get_tv_episode_direct_url(tv_id, episode_idx)
    if url:
        await query.edit_message_text(f"📺 *Episode link:*\n`{url}`", parse_mode="Markdown")
    else:
        await query.edit_message_text("❌ Failed to extract episode link.")

async def show_profile(query):
    profile = scraper.get_profile()
    data = profile.get("data", {})
    if not data:
        await query.edit_message_text("Failed to load profile.")
        return
    text = (
        f"👤 *Profile*\n"
        f"ID: `{data.get('id')}`\n"
        f"Name: {data.get('name')}\n"
        f"Email: {data.get('email')}\n"
        f"Premium expires: {data.get('premium_expired_at')}\n"
        f"Days left: {data.get('premium_life')}"
    )
    kb = [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def show_subscription(query):
    sub = scraper.get_subscription()
    data = sub.get("data", {})
    message = data.get("message", "No info available.")
    kb = [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
    await query.edit_message_text(f"💎 *Subscription*\n{message}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🎬 Latest Movies", callback_data="movies")],
        [InlineKeyboardButton("📺 Latest TV Shows", callback_data="tvshows")],
        [InlineKeyboardButton("🔍 Search Movies", callback_data="search_movies")],
        [InlineKeyboardButton("🔎 Search TV Shows", callback_data="search_tv")],
        [InlineKeyboardButton("👤 Profile", callback_data="profile")],
        [InlineKeyboardButton("💎 Subscription", callback_data="subscription")],
    ]
    await query.edit_message_text("🎬 *Bioscope Bot* – Main Menu:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# -------------------------------------------------------------------
# Search handlers (simplified, no ConversationHandler)
# We'll use a simple state stored in context.user_data
# -------------------------------------------------------------------
async def search_movies_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔍 Please send the movie keyword:")
    context.user_data['awaiting_movie_search'] = True

async def search_tv_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔎 Please send the TV show keyword:")
    context.user_data['awaiting_tv_search'] = True

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = update.message.text
    user_id = update.effective_user.id

    if context.user_data.get('awaiting_movie_search'):
        del context.user_data['awaiting_movie_search']
        await update.message.reply_text(f"Searching movies for '{keyword}'...")
        res = scraper.search_movies(keyword)
        movies = res.get("data", [])[:30]
        if not movies:
            await update.message.reply_text("No movies found.")
            return
        buttons = [[InlineKeyboardButton(m.get("title", "Unknown"), callback_data=f"movie_{m['id']}")] for m in movies]
        buttons.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")])
        await update.message.reply_text("🎬 *Search Results* – Select a movie:", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
    elif context.user_data.get('awaiting_tv_search'):
        del context.user_data['awaiting_tv_search']
        await update.message.reply_text(f"Searching TV shows for '{keyword}'...")
        res = scraper.search_tv_shows(keyword)
        shows = res.get("data", [])[:30]
        if not shows:
            await update.message.reply_text("No TV shows found.")
            return
        buttons = [[InlineKeyboardButton(s.get("title", "Unknown"), callback_data=f"tvshow_{s['id']}")] for s in shows]
        buttons.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")])
        await update.message.reply_text("📺 *Search Results* – Select a TV show:", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
    else:
        await update.message.reply_text("Please use the buttons to search or browse.")

# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------
def main():
    token = "8849115943:AAHL1pCBs9FT04qRWHMXFiwsALUhX3SFBm0"   # <-- Replace with your actual bot token
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
