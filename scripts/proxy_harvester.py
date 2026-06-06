#!/usr/bin/env python3
import asyncio
import re
import os
import json
import time
import urllib.request
import urllib.parse
import base64
import sys
from pathlib import Path
from html import unescape

# Add scripts directory to path to import check_proxies
sys.path.append(str(Path(__file__).parent))
from check_proxies import test_proxy_async, generate_clickable_link, parse_proxy_line

# Default files
STATE_FILE = "posted_proxies.json"

# Default sources of proxies
DEFAULT_SOURCES = [
    "ProxyMTProto",
    "TelgProxy",
    "socks5_list",
    "mtproto_proxies",
    "proxy_socks5_mtproto"
]

# User-Agent for web requests to bypass bot check
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_env_var(name, default=None):
    """Gets an environment variable from system or .env file."""
    val = os.getenv(name)
    if val:
        return val
    # Try reading .env file manually
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    if k.strip() == name:
                        return v.strip().strip('"').strip("'")
        except Exception:
            pass
    return default

def _gh_headers():
    token = get_env_var("GITHUB_TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "content-factory-bot",
    }

def gh_write(path: str, content: str, message: str) -> str:
    """Writes a file to GitHub repository to persist state, falling back to local write on failure."""
    token = get_env_var("GITHUB_TOKEN")
    
    # Define local write helper
    def write_local():
        p = Path(__file__).parent.parent / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, "utf-8")
        return str(p)

    if not token:
        return write_local()
        
    repo = get_env_var("GITHUB_REPO", "xopromo/content-factory")
    branch = get_env_var("GITHUB_BRANCH", "main")
    url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}"
    sha = None
    try:
        req = urllib.request.Request(url + f"?ref={branch}", headers=_gh_headers())
        with urllib.request.urlopen(req, timeout=10) as r:
            sha = json.loads(r.read()).get("sha")
    except Exception:
        pass
        
    if "[skip render]" not in message:
        message = f"{message} [skip render]"
        
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha
        
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={**_gh_headers(), "Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            result = json.loads(r.read())
            return result.get("content", {}).get("html_url", path)
    except Exception as e:
        print(f"Failed to write to GitHub ({e}). Falling back to local save.")
        return write_local()

async def telegram_api_call(method, payload):
    """Makes a request to the Telegram Bot API."""
    token = get_env_var("TG_BOT_TOKEN")
    if not token:
        print("Error: TG_BOT_TOKEN not configured.")
        return None
        
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        # Run in thread pool as urllib is blocking
        def make_req():
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode("utf-8"))
                
        return await asyncio.to_thread(make_req)
    except Exception as e:
        print(f"Telegram API {method} error: {e}")
        return None

async def scrape_channel(channel):
    """Scrapes proxy links from the public preview of a channel."""
    url = f"https://t.me/s/{channel}"
    try:
        def fetch():
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.read().decode("utf-8", errors="ignore")
                
        raw_html = await asyncio.to_thread(fetch)
        html = unescape(raw_html)
        
        # Regexes for proxy links (both tg:// and t.me/ links)
        mtproto_pattern = r'(?:tg:\/\/proxy\?server=[^"\'\s&]+&port=\d+&secret=[^"\'\s&]+|https:\/\/t\.me\/proxy\?server=[^"\'\s&]+&port=\d+&secret=[^"\'\s&]+)'
        socks_pattern = r'(?:tg:\/\/socks\?server=[^"\'\s&]+&port=\d+(?:&user=[^"\'\s&]+)?(?:&pass=[^"\'\s&]+)?|https:\/\/t\.me\/socks\?server=[^"\'\s&]+&port=\d+(?:&user=[^"\'\s&]+)?(?:&pass=[^"\'\s&]+)?)'
        
        mtproto_links = re.findall(mtproto_pattern, html)
        socks_links = re.findall(socks_pattern, html)
        
        raw_links = mtproto_links + socks_links
        normalized = []
        for link in raw_links:
            # Normalize t.me links to tg:// protocol
            normalized_link = link.replace("https://t.me/", "tg://")
            if normalized_link not in normalized:
                normalized.append(normalized_link)
                
        return normalized
    except Exception as e:
        print(f"Failed to scrape channel {channel}: {e}")
        return []

async def check_and_prune_channel(channel_username, state, timeout=5):
    """Checks already posted proxies and deletes dead posts from the channel."""
    if not state:
        return state, 0
        
    print("Checking posted proxies for pruning...")
    dead_proxies = []
    
    # Check all currently posted proxies
    for raw_link, msg_id in list(state.items()):
        proxy = parse_proxy_line(raw_link)
        if not proxy:
            # Bad format, remove from state
            del state[raw_link]
            continue
            
        is_working, latency = await test_proxy_async(proxy, timeout)
        if not is_working:
            print(f"Proxy died: {proxy['server']}:{proxy['port']}. Deleting post {msg_id}.")
            dead_proxies.append((raw_link, msg_id))
            
    # Delete posts from Telegram and update state
    deleted_count = 0
    for raw_link, msg_id in dead_proxies:
        payload = {
            "chat_id": channel_username,
            "message_id": int(msg_id)
        }
        res = await telegram_api_call("deleteMessage", payload)
        if res and res.get("ok"):
            deleted_count += 1
            print(f"Deleted message {msg_id} successfully.")
        else:
            print(f"Failed to delete message {msg_id} (it may have been deleted manually or expired).")
            
        # Always remove from state to keep it clean
        if raw_link in state:
            del state[raw_link]
            
    return state, deleted_count

async def harvest_and_post_new(channel_username, state, sources=DEFAULT_SOURCES, timeout=5, max_new_posts=10):
    """Scrapes new proxies, tests them, and posts working ones to the channel."""
    print("Scraping new proxies from sources...")
    all_new_links = []
    for source in sources:
        links = await scrape_channel(source)
        print(f"Found {len(links)} proxies in {source}")
        for link in links:
            if link not in all_new_links and link not in state:
                all_new_links.append(link)
                
    print(f"Total unique new proxies to check: {len(all_new_links)}")
    if not all_new_links:
        return state, 0
        
    # Test new proxies
    working_new = []
    semaphore = asyncio.Semaphore(15) # Concurrency limit
    
    async def worker(link):
        proxy = parse_proxy_line(link)
        if not proxy:
            return
        async with semaphore:
            success, latency = await test_proxy_async(proxy, timeout)
            if success:
                proxy["latency"] = latency
                working_new.append(proxy)
                
    await asyncio.gather(*(worker(l) for l in all_new_links))
    
    # Sort new working proxies by speed (latency)
    working_new.sort(key=lambda x: x["latency"])
    
    print(f"Found {len(working_new)} functional new proxies.")
    
    # Post to Telegram
    posted_count = 0
    for proxy in working_new:
        if posted_count >= max_new_posts:
            print(f"Reached cap of {max_new_posts} new posts per run.")
            break
            
        link = generate_clickable_link(proxy)
        ptype = proxy["type"].upper()
        server_info = f"{proxy['server']}:{proxy['port']}"
        latency_info = f"{proxy['latency']}ms"
        
        # Prepare post text
        lines = [
            f"🔌 <b>Рабочий прокси найден! [{ptype}]</b>",
            f"• <b>Сервер:</b> <code>{server_info}</code>",
            f"• <b>Пинг:</b> <code>{latency_info}</code>",
            "",
            f"📥 <a href=\"{link}\">ПОДКЛЮЧИТЬ ПРОКСИ</a>"
        ]
        text_msg = "\n".join(lines)
        
        payload = {
            "chat_id": channel_username,
            "text": text_msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        
        res = await telegram_api_call("sendMessage", payload)
        if res and res.get("ok"):
            msg_id = res["result"]["message_id"]
            state[proxy["raw"]] = msg_id
            posted_count += 1
            print(f"Posted new proxy {server_info} (Msg ID: {msg_id})")
            # Rate limit safety sleep
            await asyncio.sleep(2)
        else:
            print(f"Failed to post proxy {server_info} to channel.")
            
    return state, posted_count

def call_vk_api(method, params, token):
    """Makes a request to the VK API."""
    url = f"https://api.vk.com/method/{method}"
    full_params = {**params, "access_token": token, "v": "5.131"}
    data = urllib.parse.urlencode(full_params).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": {"error_code": -1, "error_msg": str(e)}}

def sync_to_vk(state):
    """Sends a backup list of working proxies to a VK conversation, deleting the previous message to avoid clutter."""
    token = get_env_var("VK_TOKEN")
    if not token:
        try:
            local_vk_config = Path(__file__).parent.parent.parent / "vk_config.json"
            if local_vk_config.exists():
                cfg = json.loads(local_vk_config.read_text(encoding="utf-8"))
                token = cfg.get("token")
        except Exception:
            pass
            
    if not token:
        print("VK backup skipped: VK_TOKEN not configured.")
        return
        
    if "," in token:
        token = token.split(",")[0].strip()
        
    # Get conversation peer ID (defaulting to the chat created by the user: 2000000429)
    peer_id_str = get_env_var("VK_PEER_ID", "2000000429")
    try:
        peer_id = int(peer_id_str)
    except ValueError:
        print(f"VK backup skipped: Invalid VK_PEER_ID '{peer_id_str}'")
        return
        
    import datetime
    import time
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    lines = [
        "🔌 Резервные Telegram прокси (Telegram Proxy Backup)",
        f"Обновлено: {now_str}",
        "",
        "Если Telegram не подключается из-за блокировки прокси, скопируйте одну из ссылок ниже и откройте в браузере или приложении:",
        ""
    ]
    
    idx = 1
    for raw in state.keys():
        p = parse_proxy_line(raw)
        if not p:
            continue
        link = generate_clickable_link(p)
        ptype = p["type"].upper()
        server_info = f"{p['server']}:{p['port']}"
        lines.extend([
            f"{idx}. [{ptype}] {server_info}",
            f"👉 {link}",
            ""
        ])
        idx += 1
        
    if idx == 1:
        lines.append("На данный момент нет активных прокси.")
        lines.append("")
        
    lines.append("(Этот чат обновляется автоматически каждые 20 минут)")
    message = "\n".join(lines)
    
    vk_state_file = Path(__file__).parent.parent / "vk_post_state.json"
    vk_message_id = None
    if vk_state_file.exists():
        try:
            state_data = json.loads(vk_state_file.read_text(encoding="utf-8"))
            vk_message_id = state_data.get("vk_message_id")
        except Exception:
            pass
            
    # 1. Delete previous message if it exists
    if vk_message_id:
        print(f"Deleting previous VK message {vk_message_id}...")
        del_res = call_vk_api("messages.delete", {
            "message_ids": vk_message_id,
            "delete_for_all": 1
        }, token)
        print(f"VK messages.delete response: {del_res}")
        
    # 2. Send new message
    print(f"Sending new VK message to peer {peer_id}...")
    res = call_vk_api("messages.send", {
        "peer_id": peer_id,
        "message": message,
        "random_id": int(time.time())
    }, token)
    
    success = False
    new_message_id = None
    if "response" in res:
        new_message_id = res["response"]
        print(f"Sent new backup to VK messages (Msg ID: {new_message_id})")
        success = True
    else:
        print(f"Failed to send VK message: {res}")
        
    # 3. Save state
    if success and new_message_id:
        try:
            vk_state_content = json.dumps({"vk_message_id": new_message_id}, indent=2)
            gh_write("vk_post_state.json", vk_state_content, f"chore: update VK proxy backup message state (message_id: {new_message_id})")
            print("VK message state saved.")
        except Exception as e:
            print(f"Failed to save VK message state: {e}")

async def run_harvester():
    """Main execution entry point."""
    channel_username = get_env_var("TG_PROXY_CHANNEL")
    if not channel_username:
        print("Error: TG_PROXY_CHANNEL is not configured in environment or .env.")
        return
        
    print(f"Starting harvester for channel: {channel_username}")
    
    # Load state
    state = {}
    local_state_path = Path(__file__).parent.parent / STATE_FILE
    if local_state_path.exists():
        try:
            state = json.loads(local_state_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Error reading local state: {e}")
            
    # Step 1: Prune dead proxies from channel
    state, deleted = await check_and_prune_channel(channel_username, state)
    print(f"Deleted {deleted} dead proxy posts.")
    
    # Step 2: Harvest and post new proxies
    state, posted = await harvest_and_post_new(channel_username, state)
    print(f"Posted {posted} new working proxies.")
    
    # Save state
    new_state_content = json.dumps(state, indent=2, ensure_ascii=False)
    try:
        gh_write(STATE_FILE, new_state_content, f"chore: update proxies channel state (posted: {posted}, deleted: {deleted})")
        print("State saved and pushed to GitHub.")
    except Exception as e:
        print(f"Failed to save state: {e}")

    # Synchronize backup to VK wall
    try:
        sync_to_vk(state)
    except Exception as e:
        print(f"Failed to sync proxies to VK: {e}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_harvester())
