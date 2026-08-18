import requests
import asyncio
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()

async def test_proxy(proxy_line):
    try:
        # requests uses socks5h:// to resolve DNS remotely
        proxy_url = proxy_line.replace("socks5://", "socks5h://")
        loop = asyncio.get_running_loop()
        r = await loop.run_in_executor(
            None,
            lambda: requests.get("https://github.com", proxies={"https": proxy_url, "http": proxy_url}, timeout=5)
        )
        if r.status_code == 200:
            return True, f"Success (status 200)"
        else:
            return False, f"Status code: {r.status_code}"
    except Exception as e:
        return False, f"Request failed: {e}"

async def main():
    proxy_file = ROOT / "proxies.txt"
    if not proxy_file.exists():
        print("proxies.txt not found")
        return
        
    lines = proxy_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    proxies = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
    print(f"Loaded {len(proxies)} proxies from proxies.txt")
    
    working_proxies = []
    for p in proxies[:30]: # Try top 30
        print(f"Testing {p}...")
        ok, msg = await test_proxy(p)
        if ok:
            print(f"[WORKING FOR GITHUB] {p} -> {msg}")
            working_proxies.append(p)
        else:
            print(f"[FAILED] {p} -> {msg}")
            
    if working_proxies:
        print(f"Found {len(working_proxies)} working proxies for GitHub.")
        (ROOT / "scratch" / "working_github_proxies.txt").write_text("\n".join(working_proxies), encoding="utf-8")

if __name__ == "__main__":
    asyncio.run(main())
