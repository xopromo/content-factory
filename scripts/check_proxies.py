#!/usr/bin/env python3
import asyncio
import socket
import urllib.parse
import time
import os
import sys
import socks

# Default file paths
DEFAULT_PROXY_FILE = "proxies.txt"

# Telegram DC IP addresses for testing connectivity
# DC2 (Europe) and DC4 (Europe/UK) are the most common
TELEGRAM_DCS = [
    ("149.154.167.50", 443),
    ("149.154.167.91", 443),
    ("149.154.175.53", 443),
    ("91.108.56.165", 443)
]

def parse_proxy_line(line):
    """
    Parses a proxy string into a structured dictionary.
    Supports:
    - tg://proxy?server=...&port=...&secret=...
    - https://t.me/proxy?server=...&port=...&secret=...
    - tg://socks?server=...&port=...&user=...&pass=...
    - https://t.me/socks?server=...&port=...&user=...&pass=...
    - socks5://[user:pass@]host:port
    - http://[user:pass@]host:port
    - host:port
    - host:port:user:pass
    """
    line = line.strip()
    if not line or line.startswith('#'):
        return None

    # Handle Telegram links
    if line.startswith("tg://") or line.startswith("https://t.me/"):
        try:
            parsed = urllib.parse.urlparse(line)
            # path can be empty or 'proxy'/'socks'
            q = urllib.parse.parse_qs(parsed.query)
            
            server = q.get("server", [None])[0]
            port = q.get("port", [None])[0]
            
            if not server or not port:
                # Try path if query parameters are missing (e.g. tg://proxy?...)
                # Sometimes URL parsing puts the query in path if format is weird
                if "?" in line:
                    query_str = line.split("?", 1)[1]
                    q = urllib.parse.parse_qs(query_str)
                    server = q.get("server", [None])[0]
                    port = q.get("port", [None])[0]
            
            if not server or not port:
                return None
                
            if "secret" in q:
                return {
                    "type": "mtproto",
                    "server": server,
                    "port": int(port),
                    "secret": q["secret"][0],
                    "raw": line
                }
            elif "user" in q or "pass" in q or "socks" in parsed.path or "socks" in parsed.scheme:
                return {
                    "type": "socks5",
                    "server": server,
                    "port": int(port),
                    "username": q.get("user", [None])[0],
                    "password": q.get("pass", [None])[0],
                    "raw": line
                }
            else:
                # Default to SOCKS5 if type is unclear
                return {
                    "type": "socks5",
                    "server": server,
                    "port": int(port),
                    "raw": line
                }
        except Exception:
            pass

    # Handle standard URLs
    if "://" in line:
        try:
            parsed = urllib.parse.urlparse(line)
            scheme = parsed.scheme.lower()
            if "socks5" in scheme:
                ptype = "socks5"
            elif "socks4" in scheme:
                ptype = "socks4"
            elif "http" in scheme:
                ptype = "http"
            else:
                ptype = "socks5"

            return {
                "type": ptype,
                "server": parsed.hostname,
                "port": parsed.port,
                "username": parsed.username,
                "password": parsed.password,
                "raw": line
            }
        except Exception:
            pass

    # Handle plain formats like host:port or host:port:user:pass
    parts = line.split(":")
    if len(parts) == 2:
        try:
            return {
                "type": "socks5",
                "server": parts[0],
                "port": int(parts[1]),
                "raw": line
            }
        except ValueError:
            pass
    elif len(parts) == 4:
        try:
            return {
                "type": "socks5",
                "server": parts[0],
                "port": int(parts[1]),
                "username": parts[2],
                "password": parts[3],
                "raw": line
            }
        except ValueError:
            pass

    # Fallback/last resort
    return None

def test_socks_proxy_sync(proxy, dc_ip, dc_port, timeout):
    """
    Synchronous check of a SOCKS5/SOCKS4/HTTP proxy by attempting to route to a Telegram DC.
    """
    t_start = time.time()
    try:
        s = socks.socksocket()
        s.settimeout(timeout)
        
        ptype = socks.SOCKS5
        if proxy["type"] == "socks4":
            ptype = socks.SOCKS4
        elif proxy["type"] == "http":
            ptype = socks.HTTP
            
        s.set_proxy(
            ptype,
            proxy["server"],
            proxy["port"],
            username=proxy.get("username"),
            password=proxy.get("password")
        )
        
        # Connect to Telegram DC via the proxy
        s.connect((dc_ip, dc_port))
        # Send a tiny message or just verify connect
        s.close()
        
        latency = int((time.time() - t_start) * 1000)
        return True, latency
    except Exception:
        return False, 9999

async def test_proxy_async(proxy, timeout=5):
    """
    Asynchronous proxy checker.
    """
    if not proxy:
        return False, 9999
        
    # For MTProto, we test standard TCP connection to the proxy server
    if proxy["type"] == "mtproto":
        t_start = time.time()
        try:
            # Connect directly to the proxy port
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(proxy["server"], proxy["port"]),
                timeout=timeout
            )
            
            # Send a fake HTTP request to detect if it's a web server rather than MTProto
            writer.write(b"GET / HTTP/1.1\r\n\r\n" + b"A" * 46)
            await writer.drain()
            
            # Try to read some bytes with a short timeout to see if it responds with HTTP
            try:
                data = await asyncio.wait_for(reader.read(256), timeout=1.5)
                if b"HTTP" in data or b"http" in data:
                    # It's a web server, not an MTProto proxy!
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass
                    return False, 9999
            except asyncio.TimeoutError:
                # Silent server, consistent with MTProto proxy behavior
                pass
            except Exception:
                # Connection closed or error, also consistent with MTProto proxy behavior on garbage
                pass
                
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            latency = int((time.time() - t_start) * 1000)
            return True, latency
        except Exception:
            return False, 9999
            
    # For SOCKS/HTTP, we test actual routing to a Telegram DC
    else:
        # Run the synchronous PySocks check in a thread pool to avoid blocking the async event loop
        # Try multiple DCs to prevent false negatives if one DC is temporarily down
        for dc_ip, dc_port in TELEGRAM_DCS[:2]:
            success, latency = await asyncio.to_thread(
                test_socks_proxy_sync, proxy, dc_ip, dc_port, timeout
            )
            if success:
                return True, latency
        return False, 9999

async def check_all_proxies(proxy_file=DEFAULT_PROXY_FILE, timeout=5, concurrency=20):
    """
    Reads proxies, tests them concurrently, and writes back the working ones.
    """
    if not os.path.exists(proxy_file):
        print(f"File {proxy_file} not found. Creating empty file.")
        with open(proxy_file, "w", encoding="utf-8") as f:
            pass
        return [], []

    with open(proxy_file, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    proxies = []
    for line in lines:
        parsed = parse_proxy_line(line)
        if parsed:
            proxies.append(parsed)

    if not proxies:
        return [], []

    semaphore = asyncio.Semaphore(concurrency)
    working_proxies = []
    dead_proxies = []

    async def worker(proxy):
        async with semaphore:
            success, latency = await test_proxy_async(proxy, timeout)
            if success:
                proxy["latency"] = latency
                working_proxies.append(proxy)
            else:
                dead_proxies.append(proxy)

    await asyncio.gather(*(worker(p) for p in proxies))

    # Sort working proxies by latency (fastest first)
    working_proxies.sort(key=lambda x: x["latency"])

    # Overwrite the proxy file with working ones
    with open(proxy_file, "w", encoding="utf-8") as f:
        # Write some comments first
        f.write(f"# Cleaned at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# Total: {len(proxies)} | Working: {len(working_proxies)} | Dead: {len(dead_proxies)}\n\n")
        for p in working_proxies:
            f.write(f"{p['raw']}\n")

    return working_proxies, dead_proxies

def generate_clickable_link(proxy):
    """
    Generates a tg:// link for the proxy.
    """
    if proxy["type"] == "mtproto":
        return f"tg://proxy?server={proxy['server']}&port={proxy['port']}&secret={proxy['secret']}"
    elif proxy["type"] == "socks5":
        link = f"tg://socks?server={proxy['server']}&port={proxy['port']}"
        if proxy.get("username"):
            link += f"&user={proxy['username']}"
        if proxy.get("password"):
            link += f"&pass={proxy['password']}"
        return link
    else:
        # standard URL
        return proxy["raw"]

if __name__ == "__main__":
    # If run standalone
    print("Starting proxy checker...")
    loop = asyncio.get_event_loop()
    working, dead = loop.run_until_complete(check_all_proxies())
    
    print(f"\n--- Proxy Check Results ---")
    print(f"Total checked: {len(working) + len(dead)}")
    print(f"Working: {len(working)}")
    print(f"Dead: {len(dead)}")
    
    if working:
        print("\nWorking proxies (sorted by speed):")
        for i, p in enumerate(working, 1):
            link = generate_clickable_link(p)
            print(f"{i}. [{p['type'].upper()}] {p['server']}:{p['port']} - {p['latency']}ms")
            print(f"   Link: {link}")
    else:
        print("\nNo working proxies found.")
