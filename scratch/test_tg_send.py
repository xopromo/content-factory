import sys
import os
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))

# Load dotenv
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from scripts.check_proxies import parse_proxy_line

def test_send():
    token = os.environ.get("TG_BOT_TOKEN")
    channel_id = -1004378273791
    if not token:
        print("TG_BOT_TOKEN not found.")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": channel_id,
        "text": "🤖 [Тест связи] Привет! Это Antigravity. Проверяю отправку сообщений через новые SOCKS5 прокси. Всё настроено и готово к работе!",
        "parse_mode": "HTML"
    }
    
    proxy_file = ROOT / "proxies.txt"
    if not proxy_file.exists():
        print("proxies.txt not found.")
        return
        
    lines = proxy_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    valid_proxies = []
    for line in lines:
        parsed = parse_proxy_line(line)
        if parsed and parsed.get("type") in ("socks5", "http"):
            valid_proxies.append(parsed)
            
    print(f"Found {len(valid_proxies)} proxies. Trying them...")
    
    for p in valid_proxies[:5]:
        try:
            proxy_url = ""
            if p.get("username") and p.get("password"):
                proxy_url = f"{p['type']}://{p['username']}:{p['password']}@{p['server']}:{p['port']}"
            else:
                proxy_url = f"{p['type']}://{p['server']}:{p['port']}"
                
            print(f"Trying proxy: {proxy_url}")
            
            proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
            opener = urllib.request.build_opener(proxy_handler)
            
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            
            with opener.open(req, timeout=8) as r:
                res_data = json.loads(r.read())
                print(f"Success! Message sent. ID: {res_data.get('result', {}).get('message_id')}")
                return
        except Exception as err:
            print(f"Failed with proxy {p['server']}:{p['port']}: {err}")

if __name__ == "__main__":
    test_send()
