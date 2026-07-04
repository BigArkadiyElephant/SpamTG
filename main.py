import asyncio
import os
from telethon import TelegramClient
from telethon.errors import FloodWaitError, UserPrivacyRestrictedError

# --- НАСТРОЙКИ ---
API_ID = 33163177
API_HASH = '100290ab0dfdb108d4100550810d11b8'
SESSION_NAME = 'mailing_session'

DELAY_BETWEEN = 20  # Задержка в секундах

# --- НАСТРОЙКИ ДИАПАЗОНА РАССЫЛКИ ---
# Укажи нужный диапазон (нумерация как в жизни, с 1)
START_INDEX = 1   # С какого пользователя начать (включительно)
END_INDEX = 50   # По какого пользователя идти (включительно)

BASE_FILE = 'users.txt'  # Файл с твоей базой (юзернеймы или ID)
MESSAGE = """Привет тест бота"""
async def main():
    if not os.path.exists(BASE_FILE):
        print(f"[-] Файл {BASE_FILE} не найден. Создай его рядом со скриптом.")
        return

    # Читаем всю базу
    with open(BASE_FILE, 'r', encoding='utf-8') as f:
        all_users = [line.strip() for line in f if line.strip()]

    total_in_file = len(all_users)
    if total_in_file == 0:
        print("[-] База пуста.")
        return

    print(f"[+] Всего пользователей в файле: {total_in_file}")

    # Корректируем индексы под Python (срез [start:end] не включает end, поэтому делаем подгонку)
    start = max(1, START_INDEX) - 1
    end = min(total_in_file, END_INDEX)

    # Вырезаем нужную часть базы
    users_to_send = all_users[start:end]

    if not users_to_send or start >= total_in_file:
        print("[-] Указан неверный диапазон или в него не попало ни одного пользователя.")
        return

    print(f"[+] Запуск рассылки по диапазону: с {start + 1} по {end} (итого: {len(users_to_send)} юзеров).")

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    print("[+] Сессия успешно запущена. Начинаем...\n")

    # Итерируемся по выбранным юзерам, отслеживая их реальный номер в файле для логов
    for i, user in enumerate(users_to_send, start=start + 1):
        try:
            await client.send_message(user, MESSAGE, parse_mode='markdown')
            print(f"[+] [{i}/{end}] Успешно отправлено: {user}")
            await asyncio.sleep(DELAY_BETWEEN)

        except FloodWaitError as e:
            print(f"[-] Слишком много запросов. Спим {e.seconds} секунд...")
            await asyncio.sleep(e.seconds)

        except UserPrivacyRestrictedError:
            print(f"[-] [{i}/{end}] Ошибка приватности для {user}.")

        except Exception as e:
            print(f"[-] [{i}/{end}] Не удалось отправить {user}. Ошибка: {e}")

    await client.disconnect()
    print("\n[+] Рассылка по указанному диапазону завершена!")


if __name__ == '__main__':
    asyncio.run(main())
