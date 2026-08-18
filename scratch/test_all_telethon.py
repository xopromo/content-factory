import asyncio
import sys
import logging
import collections
import time
from pathlib import Path

# Add scripts directory to path
sys.path.append(str(Path(__file__).parent.parent / "scripts"))
from check_proxies import parse_proxy_line

posted_proxies = [
    "https://t.me/proxy?server=65.109.254.108&port=443&secret=ee104462821249bd7ac519130220c25d097777772e636f6d",
    "https://t.me/proxy?server=51.250.82.46&port=443&secret=eedd104462821249bd7ac519130220c25d09",
    "https://t.me/proxy?server=95.217.222.227&port=443&secret=ee104462821249bd7ac519130220c25d0966617374646c2e636f6d",
    "https://t.me/proxy?server=159.69.100.158&port=443&secret=ee104462821249bd7ac519130220c25d0979616e6465782e7275",
    "https://t.me/proxy?server=65.109.245.52&port=7980&secret=ee104462821249bd7ac519130220c25d0979616e6465782e7275",
    "https://t.me/proxy?server=186.246.28.25&port=443&secret=ee104462821249bd7ac519130220c25d0979616e6465782e7275",
    "https://t.me/proxy?server=mc-ssh.t-proxyru.info.&port=25565&secret=ee104462821249bd7ac519130220c25d0979616e6465782e7275",
    "https://t.me/proxy?server=second.nolags.pw&port=443&secret=eedd104462821249bd7ac519130220c25d09",
    "https://t.me/proxy?server=mt.nowaboost.com&port=853&secret=eedd104462821249bd7ac519130220c25d09",
    "https://t.me/proxy?server=ghtash.co.uk&port=9965&secret=dd104462821249bd7ac519130220c25d09"
]

async def test_proxy(raw):
    p = parse_proxy_line(raw)
    if not p:
        return raw, False, "Failed to parse"
        
    from telethon import connection
    # Choose appropriate Telethon connection class based on secret or default to RandomizedIntermediate
    # If the secret is 32 chars (hex) and not starts with dd/ee, or if it is randomized:
    # Telethon connection class:
    conn_cls = connection.ConnectionTcpMTProxyRandomizedIntermediate
    
    loggers_dict = collections.defaultdict(lambda: logging.getLogger('telethon'))
    
    t_start = time.time()
    try:
        # Connect to Telegram DC 2 (or DC 4 if preferred)
        conn = conn_cls(
            ip="149.154.167.50",  # DC 2
            port=443,
            dc_id=2,
            loggers=loggers_dict,
            proxy=(p["server"], p["port"], p["secret"])
        )
        
        await asyncio.wait_for(conn.connect(), timeout=5.0)
        
        # Test if we can write and read something or if connection stays open
        # We sleep a bit to see if server drops the connection after handshake
        await asyncio.sleep(1.0)
        
        is_working = conn.is_connected()
        latency = int((time.time() - t_start) * 1000)
        await conn.disconnect()
        
        status_msg = f"Working ({latency}ms)" if is_working else "Closed immediately"
        return p["server"] + ":" + str(p["port"]), is_working, status_msg
    except Exception as e:
        return p["server"] + ":" + str(p["port"]), False, str(e)

async def main():
    print("Testing all 10 proxies with Telethon handshake...")
    tasks = [test_proxy(raw) for raw in posted_proxies]
    results = await asyncio.gather(*tasks)
    
    print("\n--- RESULTS ---")
    for host, working, msg in results:
        status = "ONLINE" if working else "OFFLINE"
        print(f"{host:<35} : {status:<10} ({msg})")

if __name__ == '__main__':
    asyncio.run(main())
