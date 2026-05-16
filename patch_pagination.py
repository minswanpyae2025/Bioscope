import re

with open("main_bot/bot.py", "r") as f:
    content = f.read()

# Update get_main_menu_keyboard with watchlist/continue watching/miniapp
menu_regex = r"(def get_main_menu_keyboard\(\):\n\s+return InlineKeyboardMarkup\(\[\n\s+\[InlineKeyboardButton\(\"🎬 ရုပ်ရှင်အသစ်များ\", callback_data=\"movies\"\)\],)"
menu_replacement = r"""def get_main_menu_keyboard():
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
    pass"""
content = re.sub(menu_regex, menu_replacement, content)

# Remove the old buttons
remove_regex = r"(\s+\[InlineKeyboardButton\(\"📺 ဇာတ်လမ်းတွဲအသစ်များ\", callback_data=\"tvshows\"\)\],\n\s+\[InlineKeyboardButton\(\"🔍 ရုပ်ရှင်ရှာရန်\", callback_data=\"search_movies\"\)\],\n\s+\[InlineKeyboardButton\(\"🔎 ဇာတ်လမ်းတွဲရှာရန်\", callback_data=\"search_tv\"\)\],\n\s+\[InlineKeyboardButton\(\"⭐ သင့်အတွက်\", callback_data=\"for_you\"\)\],\n\s+\[InlineKeyboardButton\(\"🔥 ယနေ့လူကြိုက်အများဆုံး\", callback_data=\"top_24h\"\)\],\n\s+\[InlineKeyboardButton\(\"👤 ပရိုဖိုင်\", callback_data=\"profile\"\)\],\n\s+\]\))"
content = re.sub(remove_regex, "", content)


# Handle pagination callbacks
bh_regex = r"(if data == \"movies\": await show_movies_list\(query\)\n\s+elif data == \"tvshows\": await show_tvshows_list\(query\))"
bh_replacement = r"""if data.startswith("movies_"): await show_movies_list(query, int(data.split("_")[1]))
    elif data.startswith("tvshows_"): await show_tvshows_list(query, int(data.split("_")[1]))
    elif data == "watchlist": await show_watchlist(query, update.effective_user.id)
    elif data == "continue_watching": await show_continue_watching(query, update.effective_user.id)
    elif data.startswith("add_watchlist_"): await add_to_watchlist(query, update.effective_user.id, data)"""
content = re.sub(bh_regex, bh_replacement, content)


# Replace show_movies_list
movies_list_regex = r"(async def show_movies_list\(query\):\n\s+res = await asyncio\.to_thread\(scraper\.browse_movies\)\n\s+movies = res\.get\(\"data\", \[\]\)\[:30\]\n\s+if not movies:\n\s+await query\.edit_message_text\(\"❌ မတွေ့ရှိပါ။\"\)\n\s+return\n\s+buttons = \[\[InlineKeyboardButton\(m\.get\(\"title\", \"Unknown\"\), callback_data=f\"movie_\{m\['id'\]\}\"\)\] for m in movies\]\n\s+buttons\.append\(\[InlineKeyboardButton\(\"🔙 နောက်သို့\", callback_data=\"main_menu\"\)]\)\n\s+await query\.edit_message_text\(\"🎬 \*ရုပ်ရှင်အသစ်များ\* \(ရွေးချယ်ပါ\):\", reply_markup=InlineKeyboardMarkup\(buttons\), parse_mode=\"Markdown\"\))"

movies_list_replacement = r"""async def show_movies_list(query, offset=0):
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
    await query.edit_message_text("🎬 *ရုပ်ရှင်အသစ်များ* (ရွေးချယ်ပါ):", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")"""
content = re.sub(movies_list_regex, movies_list_replacement, content)


# Replace show_tvshows_list
tvshows_list_regex = r"(async def show_tvshows_list\(query\):\n\s+res = await asyncio\.to_thread\(scraper\.browse_tv_shows\)\n\s+shows = res\.get\(\"data\", \[\]\)\[:30\]\n\s+if not shows:\n\s+await query\.edit_message_text\(\"❌ မတွေ့ရှိပါ။\"\)\n\s+return\n\s+buttons = \[\[InlineKeyboardButton\(s\.get\(\"title\", \"Unknown\"\), callback_data=f\"tvshow_\{s\['id'\]\}\"\)\] for s in shows\]\n\s+buttons\.append\(\[InlineKeyboardButton\(\"🔙 နောက်သို့\", callback_data=\"main_menu\"\)]\)\n\s+await query\.edit_message_text\(\"📺 \*ဇာတ်လမ်းတွဲအသစ်များ\* \(ရွေးချယ်ပါ\):\", reply_markup=InlineKeyboardMarkup\(buttons\), parse_mode=\"Markdown\"\))"

tvshows_list_replacement = r"""async def show_tvshows_list(query, offset=0):
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
    await query.edit_message_text("📺 *ဇာတ်လမ်းတွဲအသစ်များ* (ရွေးချယ်ပါ):", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")"""
content = re.sub(tvshows_list_regex, tvshows_list_replacement, content)


# Add to watchlist button to handle_movie_request
handle_movie_regex = r"(buttons\.append\(\[InlineKeyboardButton\(\"🔙 နောက်သို့\", callback_data=\"movies\"\)]\))"
handle_movie_replacement = r"""buttons.append([InlineKeyboardButton("📋 Save to Watchlist", callback_data=f"add_watchlist_movie_{movie_id}")])
    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="movies_0")])"""
content = re.sub(handle_movie_regex, handle_movie_replacement, content)


# Add to watchlist button to handle_tv_request
handle_tv_regex = r"(buttons\.append\(\[InlineKeyboardButton\(\"🔙 နောက်သို့\", callback_data=f\"tvshow_\{tv_id\}\"\)]\))"
handle_tv_replacement = r"""buttons.append([InlineKeyboardButton("📋 Save to Watchlist", callback_data=f"add_watchlist_tv_{tv_id}")])
    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data=f"tvshow_{tv_id}")])"""
content = re.sub(handle_tv_regex, handle_tv_replacement, content)

# update main_menu callback
tv_episodes_regex = r"callback_data=\"tvshows\""
tv_episodes_replacement = r'callback_data="tvshows_0"'
content = re.sub(tv_episodes_regex, tv_episodes_replacement, content)


with open("main_bot/bot.py", "w") as f:
    f.write(content)
