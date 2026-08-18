import sys
import datetime
sys.path.append('.')
from scripts.task_listener import gh_read_tasks, gh_write_tasks, send_telegram_reply, delete_telegram_message

tasks = gh_read_tasks()
for task in tasks:
    if task['id'] == 147:
        task['result'] = 'Отчет: Работаю в штатном режиме. Новая сессия запущена и готова к выполнению задач. Ожидаю дальнейших инструкций.'
        task['status'] = 'completed'
        task['completed_at'] = datetime.datetime.now().isoformat()
        break

gh_write_tasks(tasks)
send_telegram_reply(521, 'Привет! Всё отлично, новая сессия запущена, нахожусь в режиме готовности. Жду следующих задач!')
delete_telegram_message(522)
