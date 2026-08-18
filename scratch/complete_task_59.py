import os
import sys
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
sys.path.append(str(ROOT))

from scripts.task_listener import gh_read_tasks, gh_write_tasks, send_telegram_reply, delete_telegram_message

def main():
    task_id = 59
    msg_id = 827
    status_msg_id = 828
    
    reply_text = (
        "<b>Привет! Ответы отсутствовали из-за перезагрузки сервера и сетевых таймаутов.</b>\n\n"
        "Мы провели полную диагностику и восстановили работу системы:\n\n"
        "1. 🔌 <b>Исправлены таймауты Telegram:</b> В скрипт <code>telegram_monitor_listener.py</code> внедрена поддержка ротации SOCKS5-прокси из <code>proxies.txt</code>. Соединение успешно установлено и авторизовано.\n"
        "2. 🐙 <b>Решена проблема с Git:</b> Для предотвращения зависаний при обращениях к GitHub принудительно включено использование IPv4 (<code>force.ipresolve v4</code>). Ветви синхронизированы с remote, разрешен конфликт в <code>critical_error.json</code>.\n"
        "3. ⚙️ <b>Запущен Daemon Supervisor:</b> Процесс <code>supervisor.py</code> успешно перезапущен и контролирует все три ключевые службы:\n"
        "   • <code>websocket_client</code> (активен, слушает wakeups);\n"
        "   • <code>task_listener</code> (активен, сканирует задачи);\n"
        "   • <code>telegram_monitor_listener</code> (активен, мониторит нейроновости в реальном времени).\n\n"
        "Все службы полностью запущены и функционируют нормально!"
    )
    
    print("Reading task list...")
    tasks = gh_read_tasks()
    
    found = False
    for t in tasks:
        if t.get("id") == task_id:
            t["status"] = "completed"
            t["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            t["result"] = reply_text
            t["telegram_reply_text"] = reply_text
            t["telegram_notified"] = False # will be updated
            found = True
            break
            
    if not found:
        print(f"Task #{task_id} not found in local copy! Adding it manually to tasks.json...")
        new_task = {
            "id": task_id,
            "message_id": msg_id,
            "status_message_id": status_msg_id,
            "status": "completed",
            "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "text": "Привет",
            "result": reply_text,
            "telegram_reply_text": reply_text,
            "telegram_notified": False
        }
        tasks.append(new_task)
        
    # Attempt local Telegram notification
    print("Sending telegram reply to message 827...")
    res_id = send_telegram_reply(msg_id, reply_text)
    if res_id:
        print(f"Telegram reply sent successfully! Msg ID: {res_id}")
        for t in tasks:
            if t.get("id") == task_id:
                t["telegram_notified"] = True
                t["telegram_reply_message_id"] = res_id
    else:
        print("Telegram reply failed to send directly or via proxy.")
        
    # Attempt status message deletion
    print("Deleting status message 828...")
    deleted = delete_telegram_message(status_msg_id)
    if deleted:
        print("Status message deleted successfully.")
        for t in tasks:
            if t.get("id") == task_id:
                t["status_message_deleted"] = True
    else:
        print("Status message deletion failed or wasn't needed.")
        
    print("Saving tasks and pushing to Git...")
    gh_write_tasks(tasks, f"task: completed task #{task_id} - respond to server restart query")
    print("Task 59 completed and pushed!")

if __name__ == "__main__":
    main()
