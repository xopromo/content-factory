from pathlib import Path
ROOT = Path(__file__).parent.parent.resolve()
filepath = ROOT / "telegram_monitor_listener.log"
if filepath.exists():
    content = filepath.read_text(encoding="utf-8", errors="ignore").splitlines()
    print("=== telegram_monitor_listener.log ===")
    for line in content[-40:]:
        print(line)
else:
    print("Log not found")
