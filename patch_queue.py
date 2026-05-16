import re

with open("main_bot/bot.py", "r") as f:
    content = f.read()

# Update push logic in main_bot/bot.py
push_regex = r"(if redis_client:\n\s+q_len = redis_client\.llen\(\"leech_queue\"\)\n\s+est_mins = 2 \+ \(q_len \* 2\)\n\s+payload = \{\"internal_video_id\": internal_id, \"url\": url, \"req_id\": req_id\}\n\s+redis_client\.lpush\(\"leech_queue\", json\.dumps\(payload\)\))"
push_replacement = r"""if redis_client:
        q_len = redis_client.llen("leech_queue")
        est_mins = 2 + (q_len * 2)
        payload = {"internal_video_id": internal_id, "url": url, "req_id": req_id}

        # Check tier for queue priority
        res_user = supabase.table("users").select("tier").eq("id", user_id).execute()
        tier = res_user.data[0]['tier'] if res_user.data else "free"

        if tier == 'premium':
            redis_client.lpush("vip_queue", json.dumps(payload))
            est_mins = 0 # VIP gets instant
        else:
            redis_client.lpush("leech_queue", json.dumps(payload))"""

content = re.sub(push_regex, push_replacement, content)

with open("main_bot/bot.py", "w") as f:
    f.write(content)


with open("bot/redis_worker.py", "r") as f:
    worker_content = f.read()

# Update blpop logic in bot/redis_worker.py
blpop_regex = r"(item = await asyncio\.to_thread\(redis_client\.blpop, \"leech_queue\", timeout=0\))"
blpop_replacement = r"""item = await asyncio.to_thread(redis_client.blpop, ["vip_queue", "leech_queue"], timeout=0)"""

worker_content = re.sub(blpop_regex, blpop_replacement, worker_content)

with open("bot/redis_worker.py", "w") as f:
    f.write(worker_content)
