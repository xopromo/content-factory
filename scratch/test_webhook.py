import urllib.request
import json

def test_webhook():
    token = "8702383164:AAG6c0saDPcNK5p6IIowsi9gc_ltmCzQbng"
    url = f"https://voice-bot-ohfb.onrender.com/{token}"
    
    # Simulate a "/log" message from user chat_id 220023136
    update = {
        "update_id": 100000001,
        "message": {
            "message_id": 9999,
            "from": {
                "id": 220023136,
                "is_bot": False,
                "first_name": "Test User",
                "username": "testuser"
            },
            "chat": {
                "id": 220023136,
                "type": "private",
                "first_name": "Test User",
                "username": "testuser"
            },
            "date": 1600000000,
            "text": "/log",
            "entities": [
                {
                    "offset": 0,
                    "length": 4,
                    "type": "bot_command"
                }
            ]
        }
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(update).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print("Status Code:", resp.status)
            print("Response:", resp.read().decode("utf-8"))
    except Exception as e:
        print("Error calling webhook:", e)

if __name__ == "__main__":
    test_webhook()
