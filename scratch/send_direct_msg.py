import urllib.request
import json

def send_msg():
    token = "8702383164:AAG6c0saDPcNK5p6IIowsi9gc_ltmCzQbng"
    chat_id = "220023136"
    text = "🤖 <b>[Диагностика]</b> Привет! Я провожу диагностику бота. Если вы видите это сообщение, значит соединение с Telegram API успешно. Попробуйте отправить команду <code>/log</code> сейчас."
    
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    })
    
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload.encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print("Status:", resp.status)
            print("Response:", resp.read().decode("utf-8"))
    except Exception as e:
        print("Error sending message:", e)

if __name__ == "__main__":
    send_msg()
