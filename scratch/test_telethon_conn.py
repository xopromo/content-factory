import asyncio
import sys
import logging
import collections
from pathlib import Path

# Add scripts directory to path
sys.path.append(str(Path(__file__).parent.parent / "scripts"))

async def test_telethon_conn():
    from telethon import connection
    ConnectionTcpMTProxyRandomizedIntermediate = connection.ConnectionTcpMTProxyRandomizedIntermediate
    
    # Test proxy details (first one from the posted list)
    proxy_ip = "65.109.254.108"
    proxy_port = 443
    proxy_secret = "ee104462821249bd7ac519130220c25d097777772e636f6d"
    
    print(f"Testing connection via ConnectionTcpMTProxyRandomizedIntermediate...")
    loggers_dict = collections.defaultdict(lambda: logging.getLogger('telethon'))
    
    try:
        conn = ConnectionTcpMTProxyRandomizedIntermediate(
            ip="149.154.167.50",  # DC 2 IP
            port=443,
            dc_id=2,
            loggers=loggers_dict,
            proxy=(proxy_ip, proxy_port, proxy_secret)
        )
        
        print("Calling conn.connect()...")
        await conn.connect()
        print("Connected successfully!")
        
        # Let's wait for a second to see if the background task detects disconnection
        await asyncio.sleep(1.0)
        
        # Check if reader is at EOF
        is_eof = conn._reader.at_eof() if conn._reader else True
        print("conn._reader.at_eof():", is_eof)
        
        await conn.disconnect()
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Failed: {e}")

if __name__ == '__main__':
    asyncio.run(test_telethon_conn())
