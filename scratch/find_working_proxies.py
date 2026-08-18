import sys
import asyncio
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))

from scripts.check_proxies import check_all_proxies

async def main():
    sources = [
        ROOT / "scripts" / "grim1313_proxies.txt",
        ROOT / "scripts" / "grim1313_md_proxies.txt",
        ROOT / "scripts" / "free_socks5.txt"
    ]
    
    all_lines = []
    for src in sources:
        if src.exists():
            print(f"Reading from {src}...")
            all_lines.extend(src.read_text(encoding="utf-8", errors="ignore").splitlines())
            
    # Write temporary file to check
    temp_file = ROOT / "scratch" / "temp_proxies_to_check.txt"
    temp_file.write_text("\n".join(all_lines), encoding="utf-8")
    
    print(f"Checking {len(all_lines)} proxies...")
    working, dead = await check_all_proxies(str(temp_file), timeout=5, concurrency=50)
    
    print(f"Done! Working: {len(working)}, Dead: {len(dead)}")
    if working:
        print(f"Writing {len(working)} working proxies to ROOT/proxies.txt")
        # Overwrite ROOT / proxies.txt
        root_proxies = ROOT / "proxies.txt"
        with open(root_proxies, "w", encoding="utf-8") as f:
            f.write(f"# Collected at: {working[0].get('latency', 0)}ms\n")
            for p in working:
                f.write(f"{p['raw']}\n")
    else:
        print("No working proxies found.")

if __name__ == "__main__":
    asyncio.run(main())
