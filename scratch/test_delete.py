import asyncio
import sys
import os
from pathlib import Path

# Add scripts directory to path
sys.path.append(str(Path(__file__).parent.parent / "scripts"))
from proxy_harvester import telegram_api_call, get_env_var

async def main():
    channel = get_env_var("TG_PROXY_CHANNEL")
    token = get_env_var("TG_BOT_TOKEN")
    print(f"Channel: {channel}")
    print(f"Token (first 10 chars): {token[:10] if token else None}")
    
    if not channel or not token:
        print("Channel or token not configured.")
        return
        
    # Send test message
    payload_send = {
        "chat_id": channel,
        "text": "🤖 Тестовое сообщение от бота для проверки удаления."
    }
    print("Sending test message...")
    res_send = await telegram_api_call("sendMessage", payload_send)
    print(f"Send result: {res_send}")
    
    if res_send and res_send.get("ok"):
        msg_id = res_send["result"]["message_id"]
        print(f"Message sent successfully. ID: {msg_id}. Now attempting to delete...")
        
        # Wait 3 seconds
        await asyncio.sleep(3)
        
        payload_del = {
            "chat_id": channel,
            "message_id": msg_id
        }
        res_del = await telegram_api_call("deleteMessage", payload_del)
        print(f"Delete result: {res_del}")
    else:
        print("Failed to send test message.")

if __name__ == "__main__":
    asyncio.run(main())
