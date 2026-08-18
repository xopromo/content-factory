import asyncio
import sys
from pathlib import Path

# Public Telegram Desktop credentials (widely used for testing and custom clients)
API_ID = 6
API_HASH = "eb06d4abfb49dc3eeb1aeb98ae0f581e"

async def test_client():
    from telethon import TelegramClient, connection
    from telethon.sessions import MemorySession
    
    proxy_ip = "65.109.254.108"
    proxy_port = 443
    proxy_secret = "ee104462821249bd7ac519130220c25d097777772e636f6d"
    
    print("Testing proxy with TelegramClient and MemorySession...")
    
    # proxy format for Telethon: (type, host, port, secret)
    # type is connection.ConnectionTcpMTProxyRandomizedIntermediate
    client = TelegramClient(
        MemorySession(),
        API_ID,
        API_HASH,
        connection=connection.ConnectionTcpMTProxyRandomizedIntermediate,
        proxy=(proxy_ip, proxy_port, proxy_secret)
    )
    
    try:
        await asyncio.wait_for(client.connect(), timeout=10.0)
        print("client.connect() completed successfully!")
        
        # Check if client is actually connected
        connected = client.is_connected()
        print("client.is_connected():", connected)
        
        # Try a basic request to verify we can send/receive encrypted data
        # Since we are not logged in, we can only call help.getConfig or similar.
        # client.get_me() or help.getConfig:
        print("Retrieving server configuration (help.getConfig)...")
        from telethon.tl.functions.help import GetConfigRequest
        config = await client(GetConfigRequest())
        print("Successfully retrieved config! Number of DCs:", len(config.dc_options))
        
        print("Success! Proxy is 100% working.")
        await client.disconnect()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Failed to connect or query Telegram: {e}")
        try:
            await client.disconnect()
        except Exception:
            pass

if __name__ == '__main__':
    asyncio.run(test_client())
