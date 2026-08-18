import os
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()

def print_last_lines(filename, count=20):
    filepath = ROOT / filename
    if not filepath.exists():
        print(f"=== {filename} does not exist ===")
        return
    print(f"=== Last {count} lines of {filename} ===")
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in content[-count:]:
            print(line)
    except Exception as e:
        print(f"Failed to read {filename}: {e}")
    print("=" * 40)

if __name__ == "__main__":
    print_last_lines("supervisor.log", 30)
    print_last_lines("websocket_client.log", 30)
    print_last_lines("task_listener.log", 30)
