import asyncio
import time
import os
import sys
from pathlib import Path

# Add scripts directory to path to import check_proxies
sys.path.append(str(Path(__file__).parent.parent / "scripts"))
from check_proxies import test_proxy_async, parse_proxy_line

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

async def test_all():
    print("Testing 10 posted proxies:")
    for raw in posted_proxies:
        p = parse_proxy_line(raw)
        if not p:
            print(f"Failed to parse: {raw}")
            continue
        
        t_start = time.time()
        try:
            # Let's perform a direct connection to see if it even resolves and connects
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(p["server"], p["port"]),
                timeout=5.0
            )
            
            # Send HTTP test to see if it replies with HTTP
            writer.write(b"GET / HTTP/1.1\r\n\r\n" + b"A" * 46)
            await writer.drain()
            
            is_http = False
            response_data = b""
            try:
                response_data = await asyncio.wait_for(reader.read(256), timeout=1.5)
                if b"HTTP" in response_data or b"http" in response_data:
                    is_http = True
            except asyncio.TimeoutError:
                pass
            except Exception:
                pass
                
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
                
            latency = int((time.time() - t_start) * 1000)
            status = "WORKING" if not is_http else "FAILED (HTTP server)"
            print(f"Proxy {p['server']}:{p['port']} -> Connect SUCCESS ({latency}ms), HTTP response: {is_http}, status: {status}, response_data: {response_data}")
        except Exception as e:
            print(f"Proxy {p['server']}:{p['port']} -> Connect FAILED: {e}")

if __name__ == '__main__':
    asyncio.run(test_all())
