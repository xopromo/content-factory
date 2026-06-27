# -*- coding: utf-8 -*-
import os
import sys
import json
import time
import subprocess
import argparse
import urllib.request
import requests
from pathlib import Path
from dotenv import load_dotenv

# Setup paths
SCRIPTS_DIR = Path(__file__).parent
ROOT = SCRIPTS_DIR.parent
load_dotenv(ROOT / ".env")

sys.path.append(str(ROOT))
from scripts.task_listener import edit_telegram_status, gh_read_tasks, gh_write_tasks, git_pull

# Sibling directory
SHORTS_FACTORY_DIR = ROOT.parent / "video-shorts-factory"

def send_telegram_video(token, chat_id, video_path, caption=None, reply_to_message_id=None):
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    v_path = Path(video_path)
    if not v_path.exists():
        print(f"Error: Video file {v_path} not found.")
        return None

    # We open the file and keep it open during requests
    video_file = open(v_path, "rb")
    files = {"video": (v_path.name, video_file, "video/mp4")}
    data = {"chat_id": str(chat_id)}
    if reply_to_message_id:
        data["reply_to_message_id"] = str(reply_to_message_id)
    if caption:
        data["caption"] = caption
        data["parse_mode"] = "HTML"

    # 1. Try direct send first
    try:
        print("Trying direct send to Telegram...")
        resp = requests.post(url, data=data, files=files, timeout=90)
        if resp.status_code == 200:
            res_data = resp.json()
            if res_data.get("ok"):
                print("Direct send succeeded!")
                video_file.close()
                return res_data
            else:
                print(f"Direct send returned non-ok: {res_data}")
        else:
            print(f"Direct send returned status code: {resp.status_code}")
    except Exception as direct_err:
        print(f"Direct Telegram video send failed: {direct_err}. Attempting via proxy...")

    # 2. Try proxy fallback
    proxy_file = ROOT / "proxies.txt"
    if proxy_file.exists():
        try:
            lines = proxy_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            valid_proxies = []
            for line in lines:
                line = line.strip()
                if line.startswith("socks5://") or line.startswith("http://"):
                    valid_proxies.append(line)

            print(f"Found {len(valid_proxies)} proxies. Rotating through them...")
            import random
            random.shuffle(valid_proxies)

            for proxy in valid_proxies[:15]:
                print(f"Trying proxy: {proxy}")
                try:
                    video_file.seek(0)
                    resp = requests.post(
                        url,
                        data=data,
                        files={"video": (v_path.name, video_file, "video/mp4")},
                        proxies={"http": proxy, "https": proxy},
                        timeout=90
                    )
                    if resp.status_code == 200:
                        res_data = resp.json()
                        if res_data.get("ok"):
                            print(f"Send succeeded via proxy: {proxy}!")
                            video_file.close()
                            return res_data
                        else:
                            print(f"Proxy send returned non-ok: {res_data}")
                    else:
                        print(f"Proxy send returned status code: {resp.status_code}")
                except Exception as p_err:
                    print(f"Proxy {proxy} failed: {p_err}")
        except Exception as ex:
            print(f"Failed to read/use proxies: {ex}")

    video_file.close()
    print("All upload attempts failed.")
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="YouTube Shorts URL")
    parser.add_argument("--chat-id", required=True, help="Telegram Chat ID")
    parser.add_argument("--reply-to", type=int, help="Message ID to reply to")
    parser.add_argument("--status-msg-id", type=int, help="Telegram Status Message ID")
    parser.add_argument("--task-id", type=int, help="Git Task ID")
    parser.add_argument("--comments-count", type=int, default=7, help="Number of comments")
    parser.add_argument("--skip-original", action="store_true", help="Skip clean original search")
    parser.add_argument("--banner-type", default="base", choices=["base", "emoji"], help="Comments banner type")
    args = parser.parse_args()

    token = os.environ.get("TG_BOT_TOKEN")
    if not token:
        print("Error: TG_BOT_TOKEN not found in environment.")
        sys.exit(1)

    print(f"Starting process_shorts_telegram for URL: {args.url}")
    print(f"Chat ID: {args.chat_id}, Reply to: {args.reply_to}")

    # Set up temp output path
    output_filename = f"telegram_shorts_{int(time.time())}.mp4"
    output_path = SHORTS_FACTORY_DIR / "outputs" / output_filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Update status to 10%
    if args.status_msg_id:
        edit_telegram_status(args.status_msg_id, "⏳ <b>[10%]</b> ИИ-Агент: Начинаю скачивание видео с YouTube...")

    # 2. Prepare CLI command
    cmd = [
        sys.executable,
        "run_cli.py",
        args.url,
        "--output", str(output_path),
    ]
    if args.skip_original:
        cmd.append("--skip-original")
    else:
        cmd.append("--find-original")
        
    if args.comments_count:
        cmd.extend(["--comments-count", str(args.comments_count)])
        
    if args.banner_type:
        cmd.extend(["--banner-type", args.banner_type])

    print(f"Running CLI command: {' '.join(cmd)}")
    
    # Run process and stream output to monitor progress
    process = subprocess.Popen(
        cmd,
        cwd=str(SHORTS_FACTORY_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
        bufsize=1
    )

    current_percentage = 10
    last_status_text = ""

    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if line:
            stripped = line.strip()
            print(f"[CLI] {stripped}")
            
            # Map CLI steps to status bar updates
            status_text = None
            if "[Шаг 1/4]" in stripped:
                current_percentage = 20
                status_text = "⏳ <b>[20%]</b> ИИ-Агент: Скачивание видео с YouTube..."
            elif "[Шаг 1.5]" in stripped:
                current_percentage = 40
                status_text = "🔍 <b>[40%]</b> ИИ-Агент: Поиск чистого видео-первоисточника..."
            elif "[Шаг 2/4]" in stripped:
                current_percentage = 60
                status_text = "💬 <b>[60%]</b> ИИ-Агент: Извлечение и отбор лучших комментариев через ИИ..."
            elif "[Шаг 3/4]" in stripped:
                current_percentage = 80
                status_text = "✂️ <b>[80%]</b> ИИ-Агент: Анализ видеоряда для поиска момента стоп-кадра..."
            elif "[Шаг 4/4]" in stripped:
                current_percentage = 90
                status_text = "🎬 <b>[90%]</b> ИИ-Агент: Рендеринг финального ролика (MoviePy)..."

            if status_text and status_text != last_status_text and args.status_msg_id:
                try:
                    edit_telegram_status(args.status_msg_id, status_text)
                    last_status_text = status_text
                except Exception as se:
                    print(f"Failed to edit status: {se}")

    return_code = process.wait()
    print(f"CLI finished with code: {return_code}")

    if return_code == 0 and output_path.exists() and output_path.stat().st_size > 0:
        # Success!
        if args.status_msg_id:
            edit_telegram_status(args.status_msg_id, "📤 <b>[95%]</b> ИИ-Агент: Отправляю готовое видео в Telegram...")

        caption = "🎬 <b>Ваш Shorts ролик готов!</b>\n\nМы скачали его, нашли стоп-кадр с помощью ИИ Gemini и наложили новые ИИ-комментарии по нашим правилам."
        print(f"Uploading final video: {output_path}")
        res = send_telegram_video(token, args.chat_id, output_path, caption=caption, reply_to_message_id=args.reply_to)
        
        if res and res.get("ok"):
            print("Video successfully sent!")
            if args.status_msg_id:
                edit_telegram_status(args.status_msg_id, "✅ <b>[100%]</b> ИИ-Агент: Выполнено!")
            
            # Update task in Git
            if args.task_id:
                try:
                    git_pull()
                    tasks = gh_read_tasks()
                    for t in tasks:
                        if t.get("id") == args.task_id:
                            t["status"] = "completed"
                            t["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                            t["result"] = f"Shorts video compiled and delivered to Telegram: {output_filename}"
                            break
                    gh_write_tasks(tasks, message=f"task: completed task #{args.task_id} (shorts processing)")
                except Exception as ge:
                    print(f"Failed to update task in Git: {ge}")
        else:
            print("Failed to send video via Telegram API.")
            if args.status_msg_id:
                edit_telegram_status(args.status_msg_id, "❌ <b>[Ошибка]</b> Не удалось отправить видеофайл в Telegram.")
    else:
        # Failed!
        print(f"Processing failed. Exit code {return_code}. Output file exists: {output_path.exists()}")
        if args.status_msg_id:
            edit_telegram_status(args.status_msg_id, "❌ <b>[Ошибка]</b> Рендеринг видео завершился ошибкой.")
        
        # Send error notification
        error_url = f"https://api.telegram.org/bot{token}/sendMessage"
        err_msg = f"❌ <b>Ошибка при обработке Shorts:</b>\nКод выхода: <code>{return_code}</code>.\nПожалуйста, проверьте консольные логи."
        payload = json.dumps({"chat_id": args.chat_id, "text": err_msg, "parse_mode": "HTML", "reply_to_message_id": args.reply_to}).encode("utf-8")
        req = urllib.request.Request(error_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.getproxies = lambda: {}
            urllib.request.urlopen(req)
        except Exception:
            pass

    # Cleanup temp file
    if output_path.exists():
        try:
            pass  # output_path.unlink()  # Preserve video if upload fails
        except Exception:
            pass

if __name__ == "__main__":
    main()
