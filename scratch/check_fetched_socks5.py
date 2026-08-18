import sys
import asyncio
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))

from scripts.check_proxies import check_all_proxies

async def main():
    content_file = Path("C:/Users/асус/.gemini/antigravity/brain/53b913fe-94c5-41ad-ad76-72fde5331225/.system_generated/steps/2800/content.md")
    if not content_file.exists():
        print("Fetched proxies file not found.")
        return
        
    lines = content_file.read_text(encoding="utf-8").splitlines()
    proxy_lines = []
    for line in lines:
        line = line.strip()
        if not line or ":" not in line or line.startswith("#") or line.startswith("---") or "Source:" in line or "Title:" in line or "Description:" in line:
            continue
        proxy_lines.append(f"socks5://{line}")
        
    print(f"Parsed {len(proxy_lines)} SOCKS5 proxies.")
    
    # Take the first 300 proxies to check (to check quickly and find working ones)
    to_check = proxy_lines[:300]
    
    temp_file = ROOT / "scratch" / "socks5_to_check.txt"
    temp_file.write_text("\n".join(to_check), encoding="utf-8")
    
    print(f"Checking first {len(to_check)} proxies...")
    working, dead = await check_all_proxies(str(temp_file), timeout=4, concurrency=80)
    
    print(f"Done! Working: {len(working)}, Dead: {len(dead)}")
    if working:
        print(f"Writing {len(working)} working proxies to ROOT/proxies.txt")
        root_proxies = ROOT / "proxies.txt"
        with open(root_proxies, "w", encoding="utf-8") as f:
            f.write(f"# Collected SOCKS5 at: {working[0].get('latency', 0)}ms\n")
            for p in working:
                f.write(f"{p['raw']}\n")
    else:
        print("No working SOCKS5 proxies found.")

if __name__ == "__main__":
    asyncio.run(main())
