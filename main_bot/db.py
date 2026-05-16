import os
import redis
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
REDIS_URL = os.environ.get("REDIS_URL", "")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

redis_client = None
if REDIS_URL:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)

def get_admin_config(key, default=None):
    if not supabase: return default
    res = supabase.table('admin_config').select('value').eq('key', key).execute()
    if res.data:
        return res.data[0]['value']
    return default
