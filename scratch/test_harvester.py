import asyncio
import json
import sys
from pathlib import Path

# Add scripts directory to path
sys.path.append(str(Path(__file__).parent.parent / "scripts"))
from check_proxies import test_proxy_async, parse_proxy_line

async def main():
    state_file = Path(__file__).parent.parent / "posted_proxies.json"
    if not state_file.exists():
        print("posted_proxies.json not found")
        return
        
    with open(state_file, "r") as f:
        state = json.load(f)
        
    print(f"Loaded {len(state)} proxies from state. Testing all...")
    
    for raw_link, val in list(state.items()):
        proxy = parse_proxy_line(raw_link)
        if not proxy:
            print(f"Failed to parse {raw_link}")
            continue
            
        is_working, latency = await test_proxy_async(proxy, timeout=5)
        print(f"{proxy['server']}:{proxy['port']} : is_working={is_working}, fails={val.get('fails')}")

if __name__ == "__main__":
    asyncio.run(main())
