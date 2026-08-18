import os
import sys
import socks
import socket
import asyncio
from pathlib import Path
from telethon import TelegramClient

ROOT = Path(__file__).parent.parent.resolve()
API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"

async def test_proxy(proxy_line):
    # format: socks5://ip:port
    try:
        parts = proxy_line.strip().split("://")
        if len(parts) != 2:
            return False, "Invalid format"
        proto, addr = parts
        if "@" in addr:
            creds, ip_port = addr.split("@")
            user, passwd = creds.split(":")
            ip, port = ip_port.split(":")
        else:
            user, passwd = None, None
            ip, port = addr.split(":")
        
        port = int(port)
        proxy = (socks.SOCKS5 if proto == 'socks5' else socks.HTTP, ip, port, True, user, passwd)
        
        # Test basic connection using socket first (quick)
        loop = asyncio.get_running_loop()
        s = socks.socksocket()
        s.set_proxy(socks.SOCKS5 if proto == 'socks5' else socks.HTTP, ip, port, username=user, password=passwd)
        s.settimeout(3.0)
        try:
            await loop.run_in_executor(None, lambda: s.connect(("149.154.167.50", 443))) # Telegram DC 2
            s.close()
        except Exception as e:
            return False, f"Socket connect failed: {e}"

        # Test Telethon client
        client = TelegramClient("C:/Users/асус/telethon/temp_test_session", API_ID, API_HASH, proxy=proxy)
        await client.connect()
        connected = await client.is_user_authorized()
        await client.disconnect()
        return True, f"Success (Authorized: {connected})"
    except Exception as e:
        return False, f"Error: {e}"

async def main():
    proxy_file = ROOT / "proxies.txt"
    if not proxy_file.exists():
        print("proxies.txt not found")
        return
        
    lines = proxy_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    proxies = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
    print(f"Loaded {len(proxies)} proxies from proxies.txt")
    
    for p in proxies[:20]: # Test top 20
        print(f"Testing {p}...")
        ok, msg = await test_proxy(p)
        if ok:
            print(f"[WORKING] {p} -> {msg}")
            # Write to a file of working socks5
            (ROOT / "scratch" / "working_socks5.txt").write_text(p, encoding="utf-8")
            print("Saved working proxy to scratch/working_socks5.txt")
            return
        else:
            print(f"[FAILED] {p} -> {msg}")

if __name__ == "__main__":
    asyncio.run(main())
