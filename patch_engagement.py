import re

with open("main_bot/bot.py", "r") as f:
    content = f.read()

# 1. Add review_like and review_dislike to button_handler
bh_regex = r"(elif data.startswith\(\"add_watchlist_\"\): await add_to_watchlist\(query, update\.effective_user\.id, data\))"
bh_replacement = r"""\1
    elif data.startswith("review_"): await handle_review(query, update.effective_user.id, data)"""
content = re.sub(bh_regex, bh_replacement, content)

# 2. Add handle_review function
new_func = r"""
async def handle_review(query, user_id, data):
    parts = data.split("_")
    rating = parts[1] # 'like' or 'dislike'
    video_id = int(parts[2])

    try:
        supabase.table("user_reviews").upsert({
            "user_id": user_id,
            "video_id": video_id,
            "rating": rating
        }, on_conflict="user_id, video_id").execute()
        await query.answer("ကျေးဇူးတင်ပါသည်။", show_alert=True)
        await query.message.edit_reply_markup(reply_markup=None)
    except:
        pass
"""
content += new_func

# 3. Add auto-resolution fallback in process_video_request
# Find "if not url:"
url_fail_regex = r"(if not url:\n\s+await query\.edit_message_text\(\"❌ Error getting stream\.\"\)\n\s+return)"
url_fail_replacement = r"""if not url:
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
            STREAM_CACHE[new_cache_id] = {"stream": fallback_stream, "post_id": post_id, "is_movie": is_movie, "title": s_data.get('title', 'Bioscope Video')}

            buttons = [
                [InlineKeyboardButton(f"✅ Yes, give me {new_res}", callback_data=f"sel_{new_cache_id}")],
                [InlineKeyboardButton("🔙 No, go back", callback_data="main_menu")]
            ]
            await query.edit_message_text(f"❌ {resolution} is dead.\nWould you like {new_res} instead?", reply_markup=InlineKeyboardMarkup(buttons))
            return

        await query.edit_message_text("❌ Error getting stream. All resolutions might be dead.")
        return"""

content = re.sub(url_fail_regex, url_fail_replacement, content)

with open("main_bot/bot.py", "w") as f:
    f.write(content)
