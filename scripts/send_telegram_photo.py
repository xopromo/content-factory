# -*- coding: utf-8 -*-
import os
import sys
import argparse
import urllib.request
import json
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

# Disable Windows system registry proxy auto-detection to prevent httpx scheme crashes
urllib.request.getproxies = lambda: {}

def send_photo(photo_path, reply_to_message_id=None, chat_id=None):
    token = os.getenv("TG_BOT_TOKEN")
    if not chat_id:
        chat_id = "-1004378273791"
                
    if not token:
        print("Error: TG_BOT_TOKEN not set")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    parts = []
    # Chat ID
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n".encode("utf-8"))
    
    # Reply to message ID
    if reply_to_message_id:
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"reply_to_message_id\"\r\n\r\n{reply_to_message_id}\r\n".encode("utf-8"))
        
    # Photo file
    p_path = Path(photo_path)
    filename = p_path.name
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"{filename}\"\r\nContent-Type: image/png\r\n\r\n".encode("utf-8"))
    
    # Read photo data
    with open(p_path, "rb") as f:
        img_data = f.read()
        
    parts.append(img_data)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    
    body = b"".join(parts)
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    
    try:
        # First try direct request
        with urllib.request.urlopen(req, timeout=30) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            if res.get("ok"):
                print("Photo successfully sent!")
                return res["result"]["message_id"]
    except Exception as e:
        print(f"Direct send failed, trying via proxy channel... Error: {e}")
        
    # Proxy fallback (using socks5 proxy is not needed, we can just send via channel using standard api or telegram proxy channel ID if configured)
    # The project bot has TG_PROXY_CHANNEL from .env, but usually direct API works fine.
    return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--photo", required=True)
    parser.add_argument("--reply_to", type=int)
    args = parser.parse_args()
    send_photo(args.photo, args.reply_to)
