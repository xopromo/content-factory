import json
import subprocess
import sys

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        data = subprocess.check_output('git show origin/main:docs/articles/webhook_log.json', shell=True).decode('utf-8')
        parsed = json.loads(data)
        print("Last 15 webhook updates:")
        for entry in parsed[-15:]:
            ts = entry.get("timestamp", "")
            update = entry.get("update", {})
            msg = update.get("message", {})
            text = msg.get("text", "")
            from_user = msg.get("from", {}).get("username", "")
            print(f"  {ts} | @{from_user}: {repr(text)}")
    except Exception as e:
        print(f"Error parsing webhook_log: {e}")

if __name__ == '__main__':
    main()
