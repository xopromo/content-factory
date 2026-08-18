import json
import sys
import time
import urllib.request
import urllib.parse

def call_vk_api(method, params, token):
    url = f"https://api.vk.com/method/{method}"
    full_params = {**params, "access_token": token, "v": "5.131"}
    data = urllib.parse.urlencode(full_params).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": {"error_code": -1, "error_msg": str(e)}}

def test():
    with open('../vk_config.json', 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    token = cfg.get('token').split(',')[0].strip()
    user_id = 374982599
    
    # 1. Send message
    print("Sending message...")
    res = call_vk_api("messages.send", {
        "peer_id": user_id,
        "message": "🔌 VK Private Message test - Initial",
        "random_id": int(time.time())
    }, token)
    print("messages.send response:", res)
    
    if "response" in res:
        msg_id = res["response"]
        print(f"Message ID: {msg_id}. Waiting 3 seconds before editing...")
        time.sleep(3)
        
        # 2. Edit message
        print("Editing message...")
        edit_res = call_vk_api("messages.edit", {
            "peer_id": user_id,
            "message_id": msg_id,
            "message": "🔌 VK Private Message test - UPDATED SUCCESSFULLY!\nThis text is edited in-place."
        }, token)
        print("messages.edit response:", edit_res)

if __name__ == '__main__':
    test()
