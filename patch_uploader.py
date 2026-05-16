import re

with open("bot/helper/mirror_leech_utils/upload_utils/telegram_uploader.py", "r") as f:
    content = f.read()

# Replace the supabase update logic with Redis publish logic
db_logic_regex = r"def _update_bioscope_db_up\(msg_id, file_id, dump_msg_id\):\n\s+import redis, json\n\s+from supabase import create_client\n\s+r = redis\.from_url\(redis_url, decode_responses=True\)\n\s+sb = create_client\(sb_url, os\.environ\.get\(\"SUPABASE_KEY\", \"\"\)\)\n\s+data_str = r\.get\(f\"active_leech_\{msg_id\}\"\)\n\s+if data_str:\n\s+data = json\.loads\(data_str\)\n\s+sb\.table\(\"videos\"\)\.update\(\{\n\s+\"telegram_file_id\": file_id,\n\s+\"dump_message_id\": dump_msg_id,\n\s+\"is_alive\": True\n\s+\}\)\.eq\(\"id\", data\[\"internal_video_id\"\]\)\.execute\(\)\n\s+sb\.table\(\"user_requests\"\)\.update\(\{\"status\": \"uploaded\"\}\)\.eq\(\"id\", data\[\"req_id\"\]\)\.execute\(\)"

db_logic_replacement = r"""def _update_bioscope_db_up(msg_id, file_id, dump_msg_id):
                            import redis, json
                            r = redis.from_url(redis_url, decode_responses=True)
                            data_str = r.get(f"active_leech_{msg_id}")
                            if data_str:
                                data = json.loads(data_str)
                                payload = {
                                    "type": "video_uploaded",
                                    "internal_video_id": data["internal_video_id"],
                                    "req_id": data["req_id"],
                                    "file_id": file_id,
                                    "dump_msg_id": dump_msg_id
                                }
                                r.publish("supabase_updates", json.dumps(payload))"""

content = re.sub(db_logic_regex, db_logic_replacement, content)

with open("bot/helper/mirror_leech_utils/upload_utils/telegram_uploader.py", "w") as f:
    f.write(content)
