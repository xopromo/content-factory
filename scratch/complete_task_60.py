import os
import sys
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
sys.path.append(str(ROOT))

from scripts.task_listener import gh_read_tasks, gh_write_tasks, send_telegram_reply, delete_telegram_message

def main():
    task_id = 60
    msg_id = 830
    status_msg_id = 831
    
    reply_text = (
        "<b>Привет! Всё отлично, связь восстановлена! 😊</b>\n\n"
        "Бот не реагировал, так как произошла очередная перезагрузка сервера, которая остановила все службы, "
        "а также выявила скрытую ошибку инициализации библиотеки фильтров Telegram (<code>AttributeError</code> при обработке документов).\n\n"
        "<b>Что сделано:</b>\n"
        "1. 🛠️ <b>Исправлен баг запуска бота:</b> Ошибка фильтра документов (<code>filters.Document</code>) заменена на корректный экземпляр <code>filters.Document.ALL</code>.\n"
        "2. 🚀 <b>Обновлен GitHub:</b> Все фиксы успешно закоммичены и запушены на GitHub. Сервер Render уже автоматически обновил и запустил рабочую версию Telegram-бота.\n"
        "3. ⚙️ <b>Поднят локальный Daemon Supervisor:</b> Все фоновые службы (клиент вебсокета, монитор новостей, обработчик задач) перезапущены локально и работают в фоне.\n\n"
        "Бот снова полностью в строю и готов к работе!"
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
            t["telegram_notified"] = False
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
            "text": "Привет, привет, прием, как дела, как успеете?",
            "result": reply_text,
            "telegram_reply_text": reply_text,
            "telegram_notified": False
        }
        tasks.append(new_task)
        
    # Attempt local Telegram notification
    print("Sending telegram reply to message 830...")
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
    print("Deleting status message 831...")
    deleted = delete_telegram_message(status_msg_id)
    if deleted:
        print("Status message deleted successfully.")
        for t in tasks:
            if t.get("id") == task_id:
                t["status_message_deleted"] = True
    else:
        print("Status message deletion failed or wasn't needed.")
        
    print("Saving tasks and pushing to Git...")
    gh_write_tasks(tasks, f"task: completed task #{task_id} - respond to voice bot status query")
    print("Task 60 completed and pushed!")

if __name__ == "__main__":
    main()
