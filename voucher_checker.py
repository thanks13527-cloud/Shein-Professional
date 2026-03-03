import json
import requests
import time
import threading
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

APPLY_URL = "https://www.sheinindia.in/api/cart/apply-voucher"
RESET_URL = "https://www.sheinindia.in/api/cart/reset-voucher"

_thread_local = threading.local()
WORKERS = 5  # ⚡ 5 workers

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
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": "https://www.sheinindia.in",
        "pragma": "no-cache",
        "referer": "https://www.sheinindia.in/cart",
        "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
        "x-tenant-id": "SHEIN",
        "cookie": cookie_string
    }

def make_session():
    s = requests.Session()
    retry = Retry(total=0, connect=0, read=0, redirect=0, status=0)
    adapter = HTTPAdapter(max_retries=retry, pool_connections=100, pool_maxsize=100)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

def get_session():
    if not hasattr(_thread_local, "session"):
        cookie_string = load_cookies()
        headers = get_headers(cookie_string)
        _thread_local.session = make_session()
        _thread_local.session.headers.update(headers)
        print("✅ Session created")
    return _thread_local.session

def post_with_backoff(url, payload, max_tries=3):
    session = get_session()
    delay = 0.35
    for attempt in range(1, max_tries + 1):
        try:
            r = session.post(url, json=payload, timeout=20)
            if r.status_code in (429, 500, 502, 503, 504):
                if attempt < max_tries:
                    wait = delay * 10
                    time.sleep(wait)
                    delay *= 2
                    continue
            return r
        except requests.RequestException:
            if attempt < max_tries:
                time.sleep(delay)
                delay *= 2
                continue
            return None
    return None

def is_voucher_applicable(data):
    if not data:
        return False
    if "errorMessage" in data:
        errors = data["errorMessage"].get("errors", [])
        for error in errors:
            if error.get("type") == "VoucherOperationError":
                if "not applicable" in error.get("message", "").lower():
                    return False
        return False
    return True

def check_voucher(code, is_retry=False):
    payload = {"voucherId": code.strip(), "device": {"client_type": "web"}}
    
    r = post_with_backoff(APPLY_URL, payload, max_tries=3)
    
    if r is None:
        if not is_retry:
            return None
        return code, False, "Failed"
    
    status = r.status_code
    try:
        data = r.json()
    except:
        data = None
    
    applicable = is_voucher_applicable(data)
    
    try:
        reset_payload = {"voucherId": code.strip(), "device": {"client_type": "web"}}
        post_with_backoff(RESET_URL, reset_payload, max_tries=1)
    except:
        pass
    
    if applicable:
        return code, True, f"Applicable ({status})"
    else:
        return code, False, f"Not applicable ({status})"

def process_vouchers(vouchers, progress_callback, valid_callback, user_id):
    print(f"\n🔥 CHECKING {len(vouchers)} VOUCHERS with {WORKERS} workers\n")
    
    valid = []
    total = len(vouchers)
    start = time.time()
    
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = [executor.submit(check_voucher, code) for code in vouchers]
        
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            if result is None:
                continue
            code, ok, msg = result
            mark = "✓" if ok else "✗"
            print(f"{i}/{total} [{mark}] {code} -> {msg}")
            
            if ok:
                valid.append(code)
                valid_callback(code)
            
            progress_callback(i, total, len(valid))
    
    elapsed = time.time() - start
    print(f"\n✅ Done in {elapsed:.1f}s | Valid: {len(valid)}")
    return valid
