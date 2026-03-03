def check_voucher(code, is_retry=False):
    payload = {"voucherId": code.strip(), "device": {"client_type": "web"}}
    
    r = post_with_backoff(APPLY_URL, payload, max_tries=3)
    
    if r is None:
        if not is_retry:
            return None  # Failed, will retry in bot
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
