import re

with open("main_bot/cron.py", "r") as f:
    content = f.read()

copy_msg_regex = r"(await bot\.copy_message\(chat_id=user_id, from_chat_id=dump_id, message_id=vid\[\"dump_message_id\"\], caption=f\"\*\*\{title\}\*\*\\n\\n@BioscopeBot\", parse_mode=\"Markdown\", protect_content=True\))"
copy_msg_replacement = r"""\1
                        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                        buttons = [
                            [InlineKeyboardButton("👍 Like", callback_data=f"review_like_{vid['id']}"),
                             InlineKeyboardButton("👎 Dislike", callback_data=f"review_dislike_{vid['id']}")]
                        ]
                        await bot.send_message(chat_id=user_id, text="How was this video?", reply_markup=InlineKeyboardMarkup(buttons))"""

content = re.sub(copy_msg_regex, copy_msg_replacement, content)

with open("main_bot/cron.py", "w") as f:
    f.write(content)
