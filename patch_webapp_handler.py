import re

with open("main_bot/bot.py", "r") as f:
    content = f.read()

handler_regex = r"(app\.add_handler\(MessageHandler\(filters\.TEXT & ~filters\.COMMAND, handle_text\)\))"
handler_replacement = r"""\1
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))"""

content = re.sub(handler_regex, handler_replacement, content)

new_func = r"""
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
"""

content += new_func

with open("main_bot/bot.py", "w") as f:
    f.write(content)
