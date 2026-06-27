import asyncio
import os
import sys
import time
import requests
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.tl.types import DialogFilter, Channel
import google.generativeai as genai

# Set output encoding to UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Paths
ROOT = Path(__file__).parent.parent.resolve()
ENV_PATH = ROOT / ".env"

# Load environment
load_dotenv(ENV_PATH)
API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"
GEMINI_API_KEY = os.environ.get("GEMINI_KEY") or os.environ.get("GEMINI_API_KEY", "")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

async def rewrite_post(text):
    prompt = f"""Ты — профессиональный ИИ-редактор новостных телеграм-каналов о нейросетях.
Твоя задача — переписать (сделать качественный рерайт) исходный пост о технологиях, нейросетях или ИИ на русском языке в красивом, структурированном и привлекательном стиле.

Обязательные требования:
1. Полностью удали любую рекламу, спонсорские блоки, промокоды, скидки, призывы купить подписки или курсы.
2. Полностью удали все авторские ссылки на сторонние телеграм-каналы, чаты, ботов и призывы типа "подписывайтесь на наш канал".
3. ОБЯЗАТЕЛЬНО оставь полезные ссылки на первоисточники новостей, фактов или проектов (например, ссылки на GitHub репозитории, статьи arXiv, Hugging Face, официальные сайты проектов и демонстрации).
4. Оформи пост с использованием красивой структуры (абзацы, списки, важные термины).
5. Верни готовый очищенный и отрерайченный текст строго в формате HTML-разметки Telegram (используй <b>, <i>, <u>, <code>, <a> теги). Не используй markdown (типа **, _, `), только HTML теги.

Исходный текст поста:
{text}
"""
    # 1. Try Gemini first
    try:
        print("[AI] Attempting rewrite with Gemini...")
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, lambda: model.generate_content(prompt))
        result = response.text.strip()
        if result:
            print("[AI] Gemini rewrite success.")
            return result
    except Exception as e:
        print(f"[AI] Gemini error: {e}. Falling back to Groq...")

    # 2. Fallback to Groq API
    groq_key = os.environ.get("GROQ_KEY") or os.environ.get("GROQ_KEY_2", "")
    if not groq_key:
        print("[AI] Groq fallback failed: GROQ_KEY not found in environment.")
        return None
        
    try:
        print("[AI] Attempting rewrite with Groq (llama-3.3-70b-versatile)...")
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {groq_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        
        # Run requests in executor to keep loop non-blocking
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.post(url, json=payload, headers=headers, timeout=15)
        )
        
        if response.status_code == 200:
            data = response.json()
            result = data["choices"][0]["message"]["content"].strip()
            # Clean up potential markdown code block format wraps
            if result.startswith("```"):
                lines = result.splitlines()
                if len(lines) >= 3 and (lines[0].startswith("```html") or lines[0].startswith("```")):
                    result = "\n".join(lines[1:-1]).strip()
            print("[AI] Groq rewrite success.")
            return result
        else:
            print(f"[AI] Groq error status {response.status_code}: {response.text}")
    except Exception as ge:
        print(f"[AI] Groq fallback exception: {ge}")
        
    return None

async def main():
    if not GEMINI_API_KEY:
        print("[ERROR] GEMINI_KEY not found in environment!")
        return
        
    print("Initializing Telethon Real-time Listener (AI News Rewriter)...")
    
    # Try connecting with proxies from proxies.txt
    proxy_file = ROOT / "proxies.txt"
    proxies = []
    if proxy_file.exists():
        try:
            lines = proxy_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    import re
                    match = re.match(r'(socks5|http)://(?:([^:]+):([^@]+)@)?([^:]+):(\d+)', line)
                    if match:
                        proto, user, passwd, host, port = match.groups()
                        proxies.append((proto, host, int(port), user, passwd))
        except Exception as pe:
            print(f"Failed to load proxies list: {pe}")
            
    # Always allow a fallback to no proxy (direct connection)
    proxies.append((None, None, None, None, None))
    
    client = None
    connected = False
    
    for proto, host, port, user, passwd in proxies[:15]: # Try top 15 proxies plus direct
        proxy = None
        if proto:
            import socks
            proxy = (socks.SOCKS5 if proto == 'socks5' else socks.HTTP, host, port, True, user, passwd)
            print(f"Attempting connection using proxy: {proto}://{host}:{port} ...")
        else:
            print("Attempting direct connection ...")
            
        try:
            client = TelegramClient("C:/Users/асус/telethon/telegram_session_listener", API_ID, API_HASH, proxy=proxy)
            await client.connect()
            if await client.is_user_authorized():
                print("Successfully connected and authorized!")
                connected = True
                break
            else:
                print("[ERROR] Session exists but not authorized for this proxy/connection.")
                await client.disconnect()
        except Exception as ce:
            print(f"Connection failed using proxy: {ce}")
            if client:
                try:
                    await client.disconnect()
                except Exception:
                    pass
                    
    if not connected or not client:
        print("[CRITICAL] Could not connect to Telegram with any proxy or directly. Exiting.")
        return
    
    try:
            
        dialog_filters_obj = await client(GetDialogFiltersRequest())
        filters_list = getattr(dialog_filters_obj, 'filters', [])
        if not filters_list and isinstance(dialog_filters_obj, list):
            filters_list = dialog_filters_obj
            
        neuro_filter = None
        for f in filters_list:
            if isinstance(f, DialogFilter):
                title = f.title.text if hasattr(f.title, 'text') else str(f.title)
                if title.lower() in ["нейро", "neuro"]:
                    neuro_filter = f
                    break
                    
        if not neuro_filter:
            print("[ERROR] 'Нейро' folder not found.")
            return
            
        # Get monitored peer IDs
        peer_ids = []
        peer_titles = {}
        for peer in neuro_filter.include_peers:
            try:
                entity = await client.get_entity(peer)
                if isinstance(entity, Channel) and entity.broadcast:
                    title = getattr(entity, 'title', '').lower()
                    if any(x in title for x in ["proxy", "chat", "чат", "прокси"]):
                        continue
                    # Excluded source channels requested by user (Task 41)
                    if any(x in title for x in ["плати по миру", "рассвет", "tiktok", "тик ток", "ковровый хмель", "ковровый хмёль"]):
                        continue
                    peer_ids.append(entity.id)
                    peer_titles[entity.id] = entity.title
            except Exception:
                pass
                
        print(f"Successfully resolved {len(peer_ids)} broadcast channels for monitoring.")
        
        # Register real-time NewMessage event listener
        @client.on(events.NewMessage(chats=peer_ids))
        async def handler(event):
            msg = event.message
            if not msg:
                return
                
            # Filter short messages (less than 10 chars) if they don't have media
            has_text = msg.text and len(msg.text.strip()) > 10
            has_media = msg.media is not None
            if not has_text and not has_media:
                return
                
            channel_id = event.chat_id
            channel_title = peer_titles.get(channel_id, "Unknown Channel")
            print(f"\n[NEW MESSAGE DETECTED] Channel: '{channel_title}' (ID: {channel_id})")
            
            # Clean and rewrite the post in real-time, then send to topic
            try:
                print(f"Rewriting new post text...")
                rewritten_text = await rewrite_post(msg.text)
                if not rewritten_text:
                    print("Skipping due to rewrite failure.")
                    return
                
                temp_dir = Path("C:/Users/асус/telethon/temp_downloads")
                temp_dir.mkdir(exist_ok=True)
                
                media_file = None
                if msg.media:
                    try:
                        print("Downloading media...")
                        media_file = await client.download_media(msg, file=str(temp_dir / f"media_{msg.id}"))
                    except Exception as me:
                        print(f"Failed to download media: {me}")
                        
                to_peer = await client.get_input_entity(-1003892686118)
                sent_msg = await client.send_message(
                    to_peer,
                    rewritten_text,
                    file=media_file,
                    reply_to=2,
                    parse_mode="html"
                )
                print(f"[SUCCESS] Posted rewritten post to 'контент для всех проектов' -> 'нейроновости'. Msg ID: {sent_msg.id}")
                
                if media_file and os.path.exists(media_file):
                    os.remove(media_file)
            except Exception as fe:
                print(f"Failed to process and post message: {fe}")
        
        print("Monitoring channels in real-time. Waiting for messages...")
        await client.run_until_disconnected()
        
    except Exception as e:
        print(f"Error in monitor: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
