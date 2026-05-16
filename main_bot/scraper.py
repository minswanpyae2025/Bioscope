import requests
import json
import base64
import urllib.parse
import os
import sys
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as sym_padding

class BioscopeInteractiveScraper:
    def __init__(self, email=None, password=None):
        self.base_url = "https://cmapplication.site/api"
        self.supabase_anon_key = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIs"
            "InJlZiI6InVzZHd3ZmhrZ2Rtdnlta3VuemNwIiwicm9sZSI6ImFub24iLCJp"
            "YXQiOjE3Mjk2MzYzNjMsImV4cCI6MjA0NTIxMjM2M30.fHyFkZXzlmkO4TrOi"
            "itQ-eOL68WCio57yecF_58UwDU"
        )
        self.base_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Dart/3.0 (dart:io)",
            "X-Requested-With": "com.channelmyanmar.cmofficial",
            "Platform": "android",
            "apikey": self.supabase_anon_key,
            "X-Client-Info": "supabase-flutter/2.8.3"
        }

        self.email = email or os.environ.get("BIOSCOPE_EMAIL")
        self.password = password or os.environ.get("BIOSCOPE_PASS")
        self.device_id = "193fd949-2451-46fd-8ee1-60e4abedf041_1778848734"
        self.member_id = "494963"

        self.keys = {
            "login": "wpUkpdSGivLwIJlWnLCuo1GXyPqpUFEB%2F%2F%2FRs4uiyIL9Cvzr%2FT9BcMzHqARVWA4g1FOVUHPKyphZ65Z%2BMIFo9kmYxgr%2FfR%2BTzVEMVRspQbWVhGaAYZa9q6tVmY6UW59jD62VmzvB2FsLqhNcF2Dy3aM%2FONH8ZjiRIZSeCEYkZ1g%3D",
            "home": "wpUkpdSGivLwIJlWnLCuo1GXyPqpUFEB%2F%2F%2FRs4uiyIL9Cvzr%2FT9BcMzHqARVWA4g1FOVUHPKyphZ65Z%2BMIFo9kmYxgr%2FfR%2BTzVEMVRspQbWVhGaAYZa9q6tVmY6UW59jD62VmzvB2FsLqhNcF2Dy3aM%2FONH8ZjiRIZSeCEYkZ1g%3D",
            "movies": "l9EOMZpxrpWdBlkmjyodk6RiRZAsjwPdKw5J5SbNbO2xpzI4J1UbVihOcJ8SYrJYrrmqLpwer6Bri3veUTmxvSCjDENyORuTbIQGeLdUWHVKLUtDdyPoZwQHBvGVOA%2FdF%2Bf1LjoeoX6Fi7bHA4%2BzopuQ9T9L6Rt7VfQqe16sIrg%3D",
            "search_movies": "ffrRmJoUJqGroimlZtGbtcrx%2B6YUkIe7YpvZA1F2lK6KRw9jvaF7nUN%2Fsi2JUAs%2BPJEF%2F1t%2FGrDjf3Fpmg49PMXFHld8gp6%2BArjIq4Y23oes3DXqe60MSb8HnLZmvkoO7FAHprhMwYvabZw6Jz22HDKy7ftBvHUsNxLcIhvAaPk%3D",
            "search_tv": "UMWLiWJaglvOXs26Jtolgdz9cXTwLQL2cn5B91MocfNwh3zV2CeiAR8muN0q5wlStOi6QLHTBLUxnStLfHFNQGUTjF9MRpgJVgcfEK7BUTXR0nNCr3YoH9s%2BZ0i8kbLNpehwmppsD3u91nlO85ig6oOk30BfxPmKU%2BZOLUP%2B8qs%3D",
            "movie_detail": "GYv8p6QAzvM4%2FtXZ373zkBdWyXMz4gyKP2vMA4rLfhur32Ily9fyAQ6oUcrH3XRo1kgv7IMXY9Y4eRJLh0zPyyRh2%2BMDUC3t%2FGNQoHnVHiHoCPzLE6BQaHW3x7RINhHcNJOMNGHdKZQpRQ%2BKj%2BnW3lIH15MH85Sam6zy9W4f%2FrU%3D",
            "tv_shows": "ZIa2kN6kop4clIuLoXqYdoblRURU54NbKG44Qd45ev0ckGomdyiMqXWaOOo8ChjJgxvdH%2B3djFEOxWWBvsidfohV0RR5FDtCtGRBqffGG3FrUf0Fc1ZU1Bztd%2FZPFv%2FvlVEfhqgsbkIiaRSWTFTAvSdxRxP4lkT2hWax6d0VWyE%3D",
            "tv_detail": "3L%2BLIgztdIZhHKJrxTGrU1VOO3v546mQqkczjmaKo8nfCYkK8oCHJ8FRVW1f%2FrhZXS0EWBmH8lVITY0ZyO1i4kBcEY23g4bc9Gz%2B0ErS%2FovgSxrNd3vory1rhU99ppmSZQyInMqfcPUv7VJ6ovwr0wsxzq2Bq2mDauIo7zAiSDU%3D",
            "tv_episodes": "KO1960EcLVvrnuXN8bgGLAnZtqUwXQpUDL%2B1bjwx0RpFn2rG%2B9XF%2BIHh%2B7MX%2FJGSVIeFwifxMYtXQ4d8ui%2FrrXcKZQzbOO7YUxESS9PISINCF0zaTU2b5WrHZr%2BHiy1fzImZklD3TS9x6D5BVLRa7setQsvDUjtNJWOvWqEd8zk%3D",
            "movie_link": "vquYG%2F09Sy5ug4TiXEnwfvJknBL1EVkRZBqDb9mzEW2e8ZCTs4wv3ydqnkZI1PyZMmeof9xtHzVtFlzLBZkugkfru%2B%2B4hkXPUBiwgI1AuiebqKpAs6%2BITdQvPKu2lXG0%2FVJxFFnnYQDCmrJMUmSMScXTQUc0kdZNJB5%2FnPhfsu4%3D",
            "tv_link": "5Hs0%2B2QoQvKTq47tml2vR0ceiEnj7nSfq9cmVwnf1rPDhdM8uhS7PoCsZ62JaHnj0XTeWz%2B2EBFhtgy6vQv6dE%2Bzm25bg7ukEvuUtoFGdDkyeBE0JwXkTBDpvCwE6vBO8H4Z1XEJknO0bRxApXlF7oLveGEb66F3Gee%2BKLSMCIs%3D",
            "watch_movie": "fFa6wn61Bm2%2FE1pIAEISgP1JT06%2BsEWfI62KWSnGJro2dxz5yE9Gc%2BBumooY7N%2F7DV3m3klUu2kcBU0AgJcHADa7eom9LxAjEjhZorl16LzXDVNfH89QCjAVS4HjQ%2Fnh6eCSLQu9kUu51UKtk%2FIJhq68hoIdC7Cy9NzD3R%2BYTyk%3D",
            "watch_tv": "0WYj4z6hNG4GQToYNHVeyBDo3XPXpEGsTxyrbfSYa7RbS4cfxI%2B330GeBiiqgcY36ms0Toi9%2BTFqLX3mBBWJV3ucITG28pQfmmb6E8fCv9Mz9vS2kfPA1mdcdW9FBkS0PQ821VeTE%2BrxAOECiy6R44SjFr0XtnR7h0lHquldZQw%3D"
        }

        self.access_token = None

    def decrypt_aes_url(self, encrypted_b64):
        try:
            key = base64.b64decode("47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=")
            ciphertext = base64.b64decode(encrypted_b64)
            cipher = Cipher(algorithms.AES(key), modes.CBC(b'\x00' * 16), backend=default_backend())
            decryptor = cipher.decryptor()
            padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            unpadder = sym_padding.PKCS7(algorithms.AES.block_size).unpadder()
            plaintext_bytes = unpadder.update(padded_plaintext) + unpadder.finalize()
            raw_url = plaintext_bytes.decode('utf-8', errors='ignore')

            if "ond8.cmdrive.xyz" in raw_url: return "https://cmappsecond8.cmdrive.xyz" + raw_url.split("ond8.cmdrive.xyz")[1]
            elif "cmappsecond8.cmdrive.xyz" in raw_url: return "https://cmappsecond8.cmdrive.xyz" + raw_url.split("cmappsecond8.cmdrive.xyz")[1]
            elif "mreel.com" in raw_url: return "https://stream.cmreel.com" + raw_url.split("mreel.com")[1]
            elif "mapp.tv" in raw_url: return "https://stream.cmapp.tv" + raw_url.split("mapp.tv")[1]
            elif "appsecond8" in raw_url: return "https://cmappsecond8" + raw_url.split("appsecond8")[1]
            elif "http" in raw_url: return "http" + raw_url.split("http", 1)[1]
            return raw_url
        except Exception as e:
            return None

    def login(self):
        url = f"{self.base_url}/login?device_os=android&device_name=API_Client&device_id={self.device_id}&uuid={self.device_id}&s_key={self.keys['login']}"
        payload = {"email": self.email, "password": self.password, "rememberMe": True, "device_name": "SM-G998B", "device_os": "android", "device_id": self.device_id}
        res = requests.post(url, json=payload, headers=self.base_headers)
        if res.json().get("success"):
            self.access_token = res.json()["data"]["access_token"]
            self.base_headers["Authorization"] = f"Bearer {self.access_token}"
            return True
        return False

    def _get(self, endpoint, s_key_name, params=""):
        url = f"{self.base_url}/{endpoint}?device_os=android&device_name=API_Client&device_id={self.device_id}&uuid={self.device_id}&s_key={self.keys[s_key_name]}{params}"
        try: return requests.get(url, headers=self.base_headers).json()
        except: return {}

    def _post(self, endpoint, s_key_name, payload):
        url = f"{self.base_url}/{endpoint}?s_key={self.keys[s_key_name]}"
        try: return requests.post(url, json=payload, headers=self.base_headers).json()
        except: return {}

    def browse_movies(self, offset=0): return self._get("movies", "movies", f"&offset={offset}&is_adult=0")
    def browse_tv_shows(self, offset=0): return self._get("tv-shows", "tv_shows", f"&offset={offset}&is_adult=0")
    def search_movies(self, keyword): return self._get("search", "search_movies", f"&offset=0&is_adult=0&keyword={urllib.parse.quote(keyword)}")
    def search_tv_shows(self, keyword): return self._get("search/tv-shows", "search_tv", f"&offset=0&is_adult=0&keyword={urllib.parse.quote(keyword)}")
    def get_movie_details(self, movie_id): return self._get(f"v2/movies/{movie_id}", "movie_detail")
    def get_tv_show_details(self, tv_id): return self._get(f"v2/tv-shows/{tv_id}", "tv_detail")

    def get_you_may_also_like(self, movie_id):
        # We need a key. Let's reuse 'movies' since it might work, or extract it if necessary
        # The user provided: s_key=sXogP95OuXosrgT7cSD8dedDjpNN%2BZg5uvuqxLC5jm7pY2qxQNU6CZ3BLxVxVFlLHyvPw3Vv5GSE9%2BgEqdbzh8Nhx%2BM5kDRGsVHzlMtP7UXs%2BICJDkf9eRIhNnoeO5qGyKvzV5Hy1YOK7FYhaaFvXiYKEtuzgKsdWqXvNzN%2FP4c%3D
        custom_key = "sXogP95OuXosrgT7cSD8dedDjpNN%2BZg5uvuqxLC5jm7pY2qxQNU6CZ3BLxVxVFlLHyvPw3Vv5GSE9%2BgEqdbzh8Nhx%2BM5kDRGsVHzlMtP7UXs%2BICJDkf9eRIhNnoeO5qGyKvzV5Hy1YOK7FYhaaFvXiYKEtuzgKsdWqXvNzN%2FP4c%3D"
        url = f"{self.base_url}/you-may-also-like/movies/{movie_id}?device_os=android&device_name=API_Client&device_id={self.device_id}&uuid={self.device_id}&s_key={custom_key}&is_adult=0"
        try: return requests.get(url, headers=self.base_headers).json()
        except: return {}

    # --- NEW MULTI-STEP EXTRACTION FOR BOT ---

    def get_movie_streams(self, movie_id):
        data = self.get_movie_details(movie_id)
        movie_data = data.get("data", {})
        streams = movie_data.get("movie_streaming_links") or movie_data.get("streaming_links", [])
        return streams

    def get_tv_episodes(self, tv_id):
        tv_details = self.get_tv_show_details(tv_id)
        raw_data = tv_details.get("data", {})
        episodes = []
        if "seasons" in raw_data:
            for season in raw_data["seasons"]:
                season_name = season.get("name", f"Season {season.get('season_number', '?')}")
                for ep in season.get("episodes", []):
                    ep['_season_name'] = season_name
                    episodes.append(ep)
        elif "episodes" in raw_data: episodes = raw_data["episodes"]
        elif isinstance(raw_data, list): episodes = raw_data
        return episodes

    def get_tv_streams(self, target_ep_id):
        link_data = self._get(f"tv-shows/episodes/{target_ep_id}", "tv_episodes")
        raw_links = link_data.get("data", [])

        if isinstance(raw_links, list): streams = raw_links
        elif isinstance(raw_links, dict):
            streams = (raw_links.get("tvshow_streaming_links") or
                       raw_links.get("streaming_links") or
                       raw_links.get("tv_show_episode_streaming_links") or [])
            if not streams and "server_name" in raw_links:
                streams = [raw_links]
        else:
            streams = []
        return streams

    def extract_stream_url(self, target_stream, post_id, is_movie=True):
        payload = {
            "id": str(target_stream.get('id', '')),
            "type": target_stream.get('type', 'streaming'),
            "server_name": target_stream.get('server_name', ''),
            "device_id": self.device_id, "uuid": self.device_id, "member_id": self.member_id
        }

        endpoint = "movie/link" if is_movie else "tv-shows/episode/link"
        skey = "movie_link" if is_movie else "tv_link"
        watch_endpoint = "watch/movies" if is_movie else "watch/tv-shows"
        watch_skey = "watch_movie" if is_movie else "watch_tv"
        post_type = "movies" if is_movie else "tv-shows"

        link_res = self._post(endpoint, skey, payload)
        enc_url = link_res.get("data")

        if not enc_url and "url" in target_stream and len(target_stream["url"]) > 20:
            enc_url = target_stream["url"]

        if enc_url:
            clean_url = self.decrypt_aes_url(enc_url)
            self._post(watch_endpoint, watch_skey, {"post_id": post_id, "post_type": post_type, "member_id": self.member_id, "uuid": self.device_id})
            return clean_url
        return None
