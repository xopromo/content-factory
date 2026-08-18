import urllib.request
import json
import os
from pathlib import Path

def main():
    token = "8702383164:AAG6c0saDPcNK5p6IIowsi9gc_ltmCzQbng"
    url = f"https://voice-bot-ohfb.onrender.com/{token}"
    
    payload = {
      "update_id": 105152900,
      "message": {
        "message_id": 551,
        "from": {
          "id": 220023136,
          "is_bot": False,
          "first_name": "Константин",
          "username": "xopromo"
        },
        "chat": {
          "id": 220023136,
          "first_name": "Константин",
          "username": "xopromo",
          "type": "private"
        },
        "date": 1780321110,
        "text": "/pushlog"
      }
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            print("Status code:", response.getcode())
            print("Response:", response.read().decode('utf-8'))
    except Exception as e:
        print("Error sending webhook update:", e)

if __name__ == '__main__':
    main()
