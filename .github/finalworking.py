import requests
import json
import base64
import urllib.parse
import sys
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as sym_padding

class BioscopeInteractiveScraper:
    def __init__(self, email, password):
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
        
        self.email = email
        self.password = password
        self.device_id = "193fd949-2451-46fd-8ee1-60e4abedf041_1778848734"
        self.member_id = "494963"
        
        # --- ALL INTERCEPTED GOLDEN KEYS ---
        self.keys = {
            "login": "wpUkpdSGivLwIJlWnLCuo1GXyPqpUFEB%2F%2F%2FRs4uiyIL9Cvzr%2FT9BcMzHqARVWA4g1FOVUHPKyphZ65Z%2BMIFo9kmYxgr%2FfR%2BTzVEMVRspQbWVhGaAYZa9q6tVmY6UW59jD62VmzvB2FsLqhNcF2Dy3aM%2FONH8ZjiRIZSeCEYkZ1g%3D",
            "version": "wpUkpdSGivLwIJlWnLCuo1GXyPqpUFEB%2F%2F%2FRs4uiyIL9Cvzr%2FT9BcMzHqARVWA4g1FOVUHPKyphZ65Z%2BMIFo9kmYxgr%2FfR%2BTzVEMVRspQbWVhGaAYZa9q6tVmY6UW59jD62VmzvB2FsLqhNcF2Dy3aM%2FONH8ZjiRIZSeCEYkZ1g%3D",
            "home": "wpUkpdSGivLwIJlWnLCuo1GXyPqpUFEB%2F%2F%2FRs4uiyIL9Cvzr%2FT9BcMzHqARVWA4g1FOVUHPKyphZ65Z%2BMIFo9kmYxgr%2FfR%2BTzVEMVRspQbWVhGaAYZa9q6tVmY6UW59jD62VmzvB2FsLqhNcF2Dy3aM%2FONH8ZjiRIZSeCEYkZ1g%3D",
            "live_tv": "Ev%2F1XHONFv9nm1OEYoZVEpjOLl8sM32o6MDR095Pl8T7MO5%2Ba%2BDdu7M5qNe4P7sLjn1TihAoMQbS7nAPEytJsLtoKklGLrZI2mPZF%2FKNGZbCiMSCuCLSF1ccUCpuPbwHXl6StgyBtfIyBh0ljHuec2SOzQTY1u18rRnNnUxThrY%3D",
            "reel_tags": "Xheug2t0XBy0xAFX3FObN5UpFS8EOgRAq%2BwxPS2pFunJswNmpc%2Bl9W%2FbVUheOUQ%2Bg98KZHNjOVdij9%2BzAyJZn23OXQ5O0mZGilgU7R3Ja2jLxk%2BzjA6x40wB1XAJ9g6Y57N5c3DFbkOtAmecbOI9nAPPd7FSWuP6MzJMb3swcaY%3D",
            "subscription": "kAxHwsqepZAsWIOZJsxLhnbRL1%2BI8N8F68cXpse1baC7UkE6oAPjoERswE7mnMw7QuosFHoSrSKkdmdBJbOFNdaUr5YS0mWVxZIUyQmGrtxaeUD2NJzi4yEaOrlKvACCA4cVK2J4fFFeCfVQdA5lWHd0g9GGZpjFxVgBEuw7Z8w%3D",
            "profile": "qWim2qaIdTvPaxgF2xA5j5nA6OVWgqcy4JcsnQPRWSsCMqtTt4xi%2FAhTRrDI2QRKGbK%2FAZWUO8UjkvRo91dLdA33pYAAb2MG8XINAZ4ZFsqYfmIW1BoaGCsPR5HyP3T%2F7ZCzjDYJ6VrLuMQN5viMQsE%2F64ylsc4TUqofqkrLtjw%3D",
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

    # --- CRYPTOGRAPHY ---
    def decrypt_aes_url(self, encrypted_b64):
        key = base64.b64decode("47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=")
        ciphertext = base64.b64decode(encrypted_b64)

        cipher = Cipher(algorithms.AES(key), modes.CBC(b'\x00' * 16), backend=default_backend())
        decryptor = cipher.decryptor()
        padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        
        unpadder = sym_padding.PKCS7(algorithms.AES.block_size).unpadder()
        plaintext_bytes = unpadder.update(padded_plaintext) + unpadder.finalize()
        raw_url = plaintext_bytes.decode('utf-8', errors='ignore')
        
        if "mreel.com" in raw_url:
            return "https://stream.cmreel.com" + raw_url.split("mreel.com")[1]
        elif "mapp.tv" in raw_url:
            return "https://stream.cmapp.tv" + raw_url.split("mapp.tv")[1]
        elif "appsecond8" in raw_url:
            return "https://cmappsecond8" + raw_url.split("appsecond8")[1]
        return "[Unknown Format] " + raw_url[16:]

    # --- AUTHENTICATION ---
    def login(self):
        print("[*] Authenticating...")
        url = f"{self.base_url}/login?device_os=android&device_name=API_Client&device_id={self.device_id}&uuid={self.device_id}&s_key={self.keys['login']}"
        payload = {
            "email": self.email, "password": self.password, "rememberMe": True,
            "device_name": "SM-G998B", "device_os": "android", "device_id": self.device_id
        }
        res = requests.post(url, json=payload, headers=self.base_headers)
        
        if res.json().get("success"):
            self.access_token = res.json()["data"]["access_token"]
            self.base_headers["Authorization"] = f"Bearer {self.access_token}"
            print(f"[+] Login Successful. Access Token Acquired.\n")
            return True
        else:
            print("[-] Login failed.")
            return False

    # --- GENERIC REQUEST HANDLERS ---
    def _get(self, endpoint, s_key_name, params=""):
        url = f"{self.base_url}/{endpoint}?device_os=android&device_name=API_Client&device_id={self.device_id}&uuid={self.device_id}&s_key={self.keys[s_key_name]}{params}"
        res = requests.get(url, headers=self.base_headers)
        try:
            return res.json()
        except:
            print(f"[-] JSON Parse Error for GET {endpoint}")
            return {}

    def _post(self, endpoint, s_key_name, payload):
        url = f"{self.base_url}/{endpoint}?s_key={self.keys[s_key_name]}"
        res = requests.post(url, json=payload, headers=self.base_headers)
        try:
            return res.json()
        except:
            print(f"[-] JSON Parse Error for POST {endpoint}")
            return {}

    # --- LISTING AND SEARCH ENDPOINTS ---
    def check_version(self):
        return self._get("v2/check/version/android", "version")

    def get_home_feed(self):
        return self._get("home/mobile", "home", "&is_adult=0")

    def get_profile(self):
        return self._get("profile", "profile")

    def get_subscription(self):
        return self._get("subscription/info", "subscription")

    def get_live_tv_groups(self):
        return self._get("live/group/list-two", "live_tv", "&link_type=drm")
    
    def get_reel_tags(self):
        return self._get("reel-tags-genres", "reel_tags", "&is_adult=0")

    def browse_movies(self, offset=0):
        return self._get("movies", "movies", f"&offset={offset}&is_adult=0")

    def browse_tv_shows(self, offset=0):
        return self._get("tv-shows", "tv_shows", f"&offset={offset}&is_adult=0")

    def search_movies(self, keyword):
        encoded_kw = urllib.parse.quote(keyword)
        return self._get("search", "search_movies", f"&offset=0&is_adult=0&keyword={encoded_kw}")

    def search_tv_shows(self, keyword):
        encoded_kw = urllib.parse.quote(keyword)
        return self._get("search/tv-shows", "search_tv", f"&offset=0&is_adult=0&keyword={encoded_kw}")

    # --- DETAIL ENDPOINTS ---
    def get_movie_details(self, movie_id):
        return self._get(f"v2/movies/{movie_id}", "movie_detail")
        
    def get_tv_show_details(self, tv_id):
        return self._get(f"v2/tv-shows/{tv_id}", "tv_detail")

    # --- MEDIA EXTRACTION WORKFLOW ---
    def extract_movie_link(self, movie_id):
        print(f"\n[*] Fetching schema for Movie ID {movie_id}...")
        data = self.get_movie_details(movie_id)
        movie_data = data.get("data", {})
        streams = movie_data.get("movie_streaming_links") or movie_data.get("streaming_links", [])
        
        if not streams:
            print("[-] No streaming links found for this movie.")
            return

        target = streams[0]
        print(f"[+] Found Stream ID: {target['id']} on Server: {target['server_name']}")

        print(f"[*] Authorizing stream extraction...")
        payload = {
            "id": str(target['id']),
            "type": target.get('type', 'streaming'),
            "server_name": target.get('server_name'),
            "device_id": self.device_id, "uuid": self.device_id, "member_id": self.member_id
        }
        link_res = self._post("movie/link", "movie_link", payload)
        
        enc_url = link_res.get("data")
        
        # Fallback to embedded url if POST auth fails
        if not enc_url and "url" in target and len(target["url"]) > 20:
            enc_url = target["url"]

        if enc_url:
            print("[*] Decrypting URL...")
            clean_url = self.decrypt_aes_url(enc_url)
            print("\n" + "="*80)
            print(f"🎬 RAW MOVIE URL ({target.get('quality', 'WEB-DL')}):")
            print(clean_url)
            print("="*80 + "\n")
            self._post("watch/movies", "watch_movie", {"post_id": movie_id, "post_type": "movies", "member_id": self.member_id, "uuid": self.device_id})
        else:
            print("[-] Extraction failed.")

    def extract_tv_show_link(self, tv_id):
        # 1. Fetch TV Details to parse the REAL episode IDs
        print(f"\n[*] Fetching TV Show details for ID {tv_id}...")
        tv_details = self.get_tv_show_details(tv_id)
        
        raw_data = tv_details.get("data", {})
        if not raw_data:
            print("[-] Failed to load TV Show details.")
            return

        print(f"[+] Loaded: {raw_data.get('title', 'Unknown TV Show')}")

        episodes = []
        
        # Traverse Laravel Seasons/Episodes structure
        if "seasons" in raw_data:
            for season in raw_data["seasons"]:
                season_name = season.get("name", f"Season {season.get('season_number', '?')}")
                for ep in season.get("episodes", []):
                    ep['_season_name'] = season_name
                    episodes.append(ep)
        elif "episodes" in raw_data:
            episodes = raw_data["episodes"]
        elif isinstance(raw_data, list):
            episodes = raw_data
            
        if not episodes:
            print("[-] No episodes found in the TV Show details JSON.")
            return
            
        print("\nAvailable Episodes:")
        for idx, ep in enumerate(episodes):
            ep_num = ep.get('episode_number') or ep.get('ep_no') or ep.get('episode') or '?'
            ep_title = ep.get('title') or ep.get('name') or ep.get('ep_title') or 'Unknown'
            s_name = f"[{ep.get('_season_name')}] " if ep.get('_season_name') else ""
            print(f"  [{idx}] {s_name}Episode {ep_num} - {ep_title}")
            
        choice = input("\nEnter the bracketed number of the episode to extract: ")
        try:
            target_ep = episodes[int(choice)]
        except:
            print("[-] Invalid selection.")
            return

        target_ep_id = target_ep.get("id")
        if not target_ep_id:
            print("[-] Selected episode does not have an ID.")
            return
            
        # 2. Get the stream links for the CORRECT Episode ID
        print(f"\n[*] Fetching streaming links for Episode ID {target_ep_id}...")
        
        # FIXED: Look for 'tvshow_streaming_links' exactly as your JSON defines it
        streams = (target_ep.get("tvshow_streaming_links") or
                   target_ep.get("tv_show_episode_streaming_links") or 
                   target_ep.get("episode_streaming_links") or 
                   target_ep.get("streaming_links") or 
                   target_ep.get("links") or [])
                   
        # If links aren't embedded in details, hit the episodes endpoint
        if not streams:
            link_data = self._get(f"tv-shows/episodes/{target_ep_id}", "tv_episodes")
            raw_links = link_data.get("data", [])
            
            if isinstance(raw_links, list):
                streams = raw_links
            elif isinstance(raw_links, dict):
                streams = (raw_links.get("tvshow_streaming_links") or
                           raw_links.get("streaming_links") or 
                           raw_links.get("tv_show_episode_streaming_links") or [])
                if not streams and "server_name" in raw_links:
                    streams = [raw_links]

        # FIXED: Print raw JSON if it's completely empty so you know it's not a script error
        if not streams:
            print("[-] No streaming links exist on the backend for this episode.")
            print("[!] Raw Server Response for this Episode API call:")
            print(json.dumps(link_data, indent=2))
            return
            
        # 3. Select a streaming link (Prefer 'streaming' type over 'download')
        streaming_links = [s for s in streams if s.get("type", "") == "streaming"]
        target_stream = streaming_links[0] if streaming_links else streams[0]
            
        print(f"[+] Found Stream ID: {target_stream.get('id', '?')} on Server: {target_stream.get('server_name', 'Unknown')}")
        
        # 4. Authorize and Extract Link
        print(f"[*] Authorizing stream extraction...")
        payload = {
            "id": str(target_stream.get('id', '')),
            "type": target_stream.get('type', 'streaming'),
            "server_name": target_stream.get('server_name', ''),
            "device_id": self.device_id, "uuid": self.device_id, "member_id": self.member_id
        }
        
        link_res = self._post("tv-shows/episode/link", "tv_link", payload)
        enc_url = link_res.get("data")
        
        if not enc_url and "url" in target_stream and len(target_stream["url"]) > 20:
            print("[!] POST auth skipped or failed. Falling back to embedded payload URL...")
            enc_url = target_stream["url"]
        
        if enc_url:
            print("[*] Decrypting URL...")
            clean_url = self.decrypt_aes_url(enc_url)
            print("\n" + "="*80)
            print(f"📺 RAW EPISODE URL ({target_stream.get('quality', 'WEB-DL')}):")
            print(clean_url)
            print("="*80 + "\n")
            
            self._post("watch/tv-shows", "watch_tv", {"post_id": target_ep_id, "post_type": "tv-shows", "member_id": self.member_id, "uuid": self.device_id})
        else:
            print("[-] Extraction failed. No URL found.")

def print_menu():
    print("""
=========================================
      BIOSCOPE INTERACTIVE CONSOLE       
=========================================
  1. Browse Movies List (Latest)
  2. Browse TV Shows List (Latest)
  3. Search Movies
  4. Search TV Shows
  ---------------------------------
  5. View Movie JSON Details (v2)
  6. View TV Show JSON Details (v2)
  ---------------------------------
  7. Extract Media: Movie (.mkv/.m3u8)
  8. Extract Media: TV Show Episode
  ---------------------------------
  9. View Profile Details
 10. View Subscription Info
 11. Get Live TV Groups
 12. Get Reel Tags
 13. Check API Version
  0. Exit
=========================================
""")

if __name__ == "__main__":
    scraper = BioscopeInteractiveScraper(email="kt20202004@gmail.com", password="#Zawzaw123")
    
    if not scraper.login():
        sys.exit()

    while True:
        print_menu()
        choice = input("Select an option: ")
        
        if choice == '0':
            print("Exiting...")
            break
            
        elif choice == '1':
            res = scraper.browse_movies()
            print("\n--- LATEST MOVIES ---")
            for m in res.get("data", [])[:15]:
                print(f"[{m['id']}] {m.get('title')}")
                
        elif choice == '2':
            res = scraper.browse_tv_shows()
            print("\n--- LATEST TV SHOWS ---")
            for t in res.get("data", [])[:15]:
                print(f"[{t['id']}] {t.get('title')}")
                
        elif choice == '3':
            kw = input("Enter movie keyword: ")
            res = scraper.search_movies(kw)
            print("\n--- SEARCH RESULTS ---")
            for m in res.get("data", []):
                print(f"[{m['id']}] {m.get('title')}")
                
        elif choice == '4':
            kw = input("Enter TV show keyword: ")
            res = scraper.search_tv_shows(kw)
            print("\n--- SEARCH RESULTS ---")
            for t in res.get("data", []):
                print(f"[{t['id']}] {t.get('title')}")

        elif choice == '5':
            m_id = input("Enter Movie ID: ")
            if m_id.isdigit():
                print(json.dumps(scraper.get_movie_details(m_id), indent=2))
                
        elif choice == '6':
            t_id = input("Enter TV Show ID: ")
            if t_id.isdigit():
                print(json.dumps(scraper.get_tv_show_details(t_id), indent=2))
                
        elif choice == '7':
            m_id = input("Enter Movie ID: ")
            if m_id.isdigit(): scraper.extract_movie_link(m_id)
            
        elif choice == '8':
            t_id = input("Enter TV Show ID: ")
            if t_id.isdigit(): scraper.extract_tv_show_link(t_id)
            
        elif choice == '9':
            print(json.dumps(scraper.get_profile(), indent=2))
            
        elif choice == '10':
            print(json.dumps(scraper.get_subscription(), indent=2))
            
        elif choice == '11':
            print(json.dumps(scraper.get_live_tv_groups(), indent=2))
            
        elif choice == '12':
            print(json.dumps(scraper.get_reel_tags(), indent=2))
            
        elif choice == '13':
            print(json.dumps(scraper.check_version(), indent=2))
            
        else:
            print("[-] Invalid choice.")
