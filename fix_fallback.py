with open("main_bot/bot.py", "r") as f:
    content = f.read()

content = content.replace("\"title\": s_data.get('title', 'Bioscope Video')", "\"title\": data.get('title', 'Bioscope Video')")
content = content.replace("on_conflict=\"user_id, video_id\"", "on_conflict=\"user_id,video_id\"")

with open("main_bot/bot.py", "w") as f:
    f.write(content)
