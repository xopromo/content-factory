import asyncio, sys
sys.path.append(r"c:/Users/асус/Desktop/клод/антигравити, всякое/content-factory/scripts")
from proxy_harvester import scrape_channel

async def main():
    channels = ["mtp4tg", "MTProxyT", "mtproxyx", "ProxyFree_Ru", "ProxyMTProto", "TProxyRU"]
    for ch in channels:
        try:
            links = await scrape_channel(ch)
            print(f"Channel {ch}: {len(links)} proxies")
            if links:
                for l in links[:5]:
                    print("  ", l)
        except Exception as e:
            print(f"Channel {ch} error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
