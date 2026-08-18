import os
import sys
import urllib.request
import json
from pathlib import Path

# Load env variables
ROOT = Path(__file__).parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

token = os.getenv("TG_BOT_TOKEN")
if not token:
    print("No TG_BOT_TOKEN in env")
    sys.exit(1)

url = f"https://api.telegram.org/bot{token}/getMe"
try:
    with urllib.request.urlopen(url, timeout=10) as response:
        data = json.loads(response.read().decode())
        print("Bot getMe response:", json.dumps(data, indent=2, ensure_ascii=False))
except Exception as e:
    print(f"Error calling Telegram API: {e}")
