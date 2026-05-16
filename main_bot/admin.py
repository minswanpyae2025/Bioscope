from telegram import Update
from telegram.ext import ContextTypes
from db import supabase, get_admin_config
import os

ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

async def set_dump_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args:
        await update.message.reply_text("Usage: /set_dump_channel -100xxx")
        return
    val = context.args[0]
    supabase.table("admin_config").upsert({"key": "dump_channel_id", "value": val}).execute()
    await update.message.reply_text(f"Dump channel set to {val}")

async def set_trash_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args:
        await update.message.reply_text("Usage: /set_trash_channel -100xxx")
        return
    val = context.args[0]
    supabase.table("admin_config").upsert({"key": "trash_channel_id", "value": val}).execute()
    await update.message.reply_text(f"Trash channel set to {val}")

async def set_required_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args:
        await update.message.reply_text("Usage: /set_required_channels -100xxx,-100yyy")
        return
    import json
    val = context.args[0].split(",")
    supabase.table("admin_config").upsert({"key": "required_channels", "value": json.dumps(val)}).execute()
    await update.message.reply_text(f"Required channels set to {val}")

async def add_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not update.message.reply_to_message or not update.message.reply_to_message.video:
        await update.message.reply_text("Please reply to a video with /add_ad <required_seconds> <reward_tokens> | <Title> | <Text> | <InlineLink>")
        return
    try:
        parts = " ".join(context.args).split("|")
        req_sec, rew_tok = parts[0].strip().split(" ")
        title = parts[1].strip()
        text = parts[2].strip()
        link = parts[3].strip() if len(parts) > 3 else "#"
        file_id = update.message.reply_to_message.video.file_id

        supabase.table("ads").insert({
            "title": title, "video_file_id": file_id, "text": text,
            "inline_link": link, "required_watch_seconds": int(req_sec), "reward_tokens": int(rew_tok)
        }).execute()

        ad_res = supabase.table("ads").select("id").order("id", desc=True).limit(1).execute()
        if ad_res.data:
            supabase.table("admin_config").upsert({"key": "default_ad_id", "value": str(ad_res.data[0]['id'])}).execute()

        await update.message.reply_text("Ad added and set as default.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
