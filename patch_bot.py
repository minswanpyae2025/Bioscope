import re

with open("main_bot/bot.py", "r") as f:
    content = f.read()

# Add buy_premium to show_profile
profile_regex = r"(txt \+= f\"Premium Exp: \{user\['premium_expires_at'\]\}\\n\")\n\s+await query\.edit_message_text\(txt, reply_markup=InlineKeyboardMarkup\(\[\[InlineKeyboardButton\(\"🔙 နောက်သို့\", callback_data=\"main_menu\"\)]]\), parse_mode=\"Markdown\"\)"

profile_replacement = r"""\1
    buttons = []
    if user['tier'] != 'premium':
        buttons.append([InlineKeyboardButton("💎 Buy Premium (100 Tokens)", callback_data="buy_premium")])
    buttons.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="main_menu")])
    await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")"""

content = re.sub(profile_regex, profile_replacement, content)

# Add callback handler for buy_premium
btn_handler_regex = r"(elif data == \"top_24h\": await show_top_24h\(query\))"
btn_handler_replacement = r"""\1
    elif data == "buy_premium": await handle_buy_premium(query, update.effective_user.id)"""

content = re.sub(btn_handler_regex, btn_handler_replacement, content)

# Add handle_buy_premium function
new_func = r"""
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
"""

content += new_func

with open("main_bot/bot.py", "w") as f:
    f.write(content)
