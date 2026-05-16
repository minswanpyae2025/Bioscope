with open("main_bot/bot.py", "r") as f:
    content = f.read()

content = content.replace("f\"❌ {resolution} is dead.\nWould you like {new_res} instead?\"", "f\"❌ {resolution} is dead.\\nWould you like {new_res} instead?\"")

with open("main_bot/bot.py", "w") as f:
    f.write(content)
