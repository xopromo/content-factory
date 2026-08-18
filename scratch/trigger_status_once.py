import urllib.request
import json
import time
import sys

def trigger_status():
    url = 'https://voice-bot-ohfb.onrender.com/8702383164:AAG6c0saDPcNK5p6IIowsi9gc_ltmCzQbng'
    update_id = 2000000000 + int(time.time()) % 100000000
    payload = {
        'update_id': update_id,
        'message': {
            'message_id': 999997,
            'from': {'id': 220023136, 'is_bot': False, 'first_name': 'User'},
            'chat': {'id': 220023136, 'type': 'private'},
            'date': int(time.time()),
            'text': '/status',
            'entities': [{'offset': 0, 'length': 7, 'type': 'bot_command'}]
        }
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    try:
        r = urllib.request.urlopen(req, timeout=30)
        return r.status, r.read().decode('utf-8')
    except Exception as e:
        return None, str(e)

def main():
    print("Triggering /status via webhook...")
    status, response = trigger_status()
    print(f"Status: {status}")
    print(f"Response: {response}")

if __name__ == '__main__':
    main()
