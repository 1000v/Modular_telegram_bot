from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CommandHandler, CallbackQueryHandler
import os
import shutil
from datetime import datetime
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import logging
import hashlib
import aiohttp
import json
from typing import Optional, Tuple
import random

logger = logging.getLogger(__name__)

COMMAND = 'files'
COMMAND_DESCRIPTION = 'Файловый менеджер (Windows)'

__version__ = "1.0.0"
__doc__ = "Файловый менеджер (Windows)"
__dependencies__ = ["aiohttp", "shutil"]  # optional

# Защита от спама: минимальный интервал между командами (в секундах)
SPAM_INTERVAL = 5
last_command_time = {}

# Локальный пул потоков для файловых операций
file_thread_pool = ThreadPoolExecutor(max_workers=4)

# Хранилище путей
path_cache = {}

def generate_path_id(path: str) -> str:
    """Генерирует короткий ID для пути"""
    hash_object = hashlib.md5(path.encode())
    return hash_object.hexdigest()[:8]

def store_path(path: str) -> str:
    """Сохраняет путь и возвращает его ID"""
    path_id = generate_path_id(path)
    path_cache[path_id] = path
    return path_id

def get_path(path_id: str) -> str:
    """Получает путь по его ID"""
    return path_cache.get(path_id)

@lru_cache(maxsize=10)
def get_drives():
    """Получить список доступных дисков (кэшируется)"""
    return [f"{d}:\\" for d in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" 
            if os.path.exists(f"{d}:")]

def check_spam(user_id: int, command_type: str = "command") -> bool:
    """
    Проверка на спам
    command_type: 
        - "command" - основные команды (требуют задержки)
        - "navigation" - навигация (без задержки)
    """
    if command_type == "navigation":
        return False
        
    current_time = time.time()
    if user_id in last_command_time:
        if current_time - last_command_time[user_id] < SPAM_INTERVAL:
            return True
    last_command_time[user_id] = current_time
    return False

def format_size(size: int) -> str:
    """Форматирование размера файла"""
    for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} ТБ"

async def get_directory_contents(path: str):
    """Асинхронное получение содержимого директории"""
    try:
        loop = asyncio.get_event_loop()
        items = await loop.run_in_executor(file_thread_pool, os.listdir, path)
        
        dirs = []
        files = []
        
        async def process_item(item):
            try:
                full_path = os.path.join(path, item)
                if await loop.run_in_executor(file_thread_pool, os.path.isdir, full_path):
                    dirs.append((item, store_path(full_path)))
                else:
                    files.append((item, store_path(full_path)))
            except (PermissionError, FileNotFoundError):
                pass

        tasks = [process_item(item) for item in items]
        await asyncio.gather(*tasks)
                
        return sorted(dirs), sorted(files)
    except Exception as e:
        logger.error(f"Ошибка при чтении директории {path}: {e}")
        return [], []

async def read_file_content(path: str, max_size: int = 1024 * 1024) -> tuple[str, bool]:
    """Асинхронное чтение файла"""
    try:
        loop = asyncio.get_event_loop()
        size = await loop.run_in_executor(file_thread_pool, os.path.getsize, path)
        
        if size > max_size:
            return "Файл слишком большой для отображения", False
            
        async def read_file():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read(4000)  # Ограничение Telegram
            except UnicodeDecodeError:
                raise ValueError("Бинарный файл")
                
        content = await loop.run_in_executor(file_thread_pool, read_file)
        truncated = len(content) >= 4000
        
        if truncated:
            content = content[:4000] + "\n... (обрезано)"
            
        return content, truncated
    except ValueError as e:
        raise
    except Exception as e:
        logger.error(f"Ошибка при чтении файла {path}: {e}")
        raise

async def delete_item(path: str) -> bool:
    """Асинхронное удаление файла/папки"""
    try:
        loop = asyncio.get_event_loop()
        if await loop.run_in_executor(file_thread_pool, os.path.isfile, path):
            await loop.run_in_executor(file_thread_pool, os.remove, path)
        else:
            await loop.run_in_executor(file_thread_pool, shutil.rmtree, path)
        return True
    except Exception as e:
        logger.error(f"Ошибка при удалении {path}: {e}")
        return False

async def list_directory(update: Update, context, current_path=None):
    """Отдельная функция для отображения содержимого директории"""
    query = update.callback_query
    
    if not current_path:
        # Показываем список дисков
        keyboard = []
        for drive in get_drives():
            drive_id = store_path(drive)
            keyboard.append([InlineKeyboardButton(
                f"💿 Диск {drive}", 
                callback_data=f"files_open:{drive_id}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="files_back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите диск:", reply_markup=reply_markup)
        return

    # Показываем содержимое текущей папки
    dirs, files = await get_directory_contents(current_path)
    keyboard = []
    
    # Добавляем папки
    for name, path_id in dirs:
        keyboard.append([InlineKeyboardButton(
            f"📁 {name[:30]}", 
            callback_data=f"files_open:{path_id}"
        )])
    
    # Добавляем файлы
    for name, path_id in files:
        keyboard.append([InlineKeyboardButton(
            f"📄 {name[:30]}", 
            callback_data=f"files_open:{path_id}"
        )])
    
    # Кнопка "Вверх"
    parent = os.path.dirname(current_path)
    if parent != current_path:
        parent_id = store_path(parent)
        keyboard.append([InlineKeyboardButton(
            "⬆️ Вверх", 
            callback_data=f"files_open:{parent_id}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 В главное меню", callback_data="files_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📂 Папка: {current_path}\nФайлов: {len(files)}, Папок: {len(dirs)}",
        reply_markup=reply_markup
    )

async def handle_button(update: Update, context):
    """Обработчик нажатия кнопки модуля"""
    query = update.callback_query
    
    try:
        data = query.data
        user_id = update.effective_user.id

        # Определяем тип команды
        command_type = "navigation" if data.startswith(("files_list", "files_open:")) else "command"
        
        if check_spam(user_id, command_type):
            await query.answer("Подождите немного перед следующей командой!", show_alert=True)
            return

        if data == "files_list":
            current_path = context.user_data.get('current_path')
            await list_directory(update, context, current_path)

        elif data.startswith("files_open:"):
            path_id = data.split(":", 1)[1]
            path = get_path(path_id)
            if not path:
                await query.answer("Ошибка: путь не найден", show_alert=True)
                return
                
            context.user_data['current_path'] = path
            
            loop = asyncio.get_event_loop()
            is_file = await loop.run_in_executor(file_thread_pool, os.path.isfile, path)
            
            if is_file:
                # Информация о файле
                stats = await loop.run_in_executor(file_thread_pool, os.stat, path)
                text = (
                    f"📄 Файл: {os.path.basename(path)}\n"
                    f"📦 Размер: {format_size(stats.st_size)}\n"
                    f"📅 Изменен: {datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}"
                )
                
                keyboard = [
                    [
                        InlineKeyboardButton("⬇️ Скачать", callback_data=f"files_download:{path_id}"),
                        InlineKeyboardButton("▶️ Запустить", callback_data=f"files_launch:{path_id}")
                    ],
                    [InlineKeyboardButton("📂 Назад", callback_data="files_list")]
                ]
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.message.edit_text(text, reply_markup=reply_markup)
            else:
                # Переходим в папку
                await list_directory(update, context, path)

        elif data.startswith("files_download:"):
            path_id = data.split(":", 1)[1]
            path = get_path(path_id)
            if path:
                await handle_file_download(update, context, path)
            else:
                await query.answer("Ошибка: файл не найден", show_alert=True)

        elif data.startswith("files_launch:"):
            path_id = data.split(":", 1)[1]
            path = get_path(path_id)
            if path:
                success, message = await launch_file(path)
                await query.answer(message, show_alert=True)
            else:
                await query.answer("Ошибка: файл не найден", show_alert=True)

        elif data.startswith("files_read:"):
            path_id = data.split(":", 1)[1]
            path = get_path(path_id)
            if not path:
                await query.answer("Ошибка: путь не найден", show_alert=True)
                return
                
            try:
                content, truncated = await read_file_content(path)
                keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f"files_open:{path_id}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"📄 {os.path.basename(path)}:\n\n```\n{content}\n```",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            except ValueError as e:
                await query.answer(str(e), show_alert=True)
            except Exception as e:
                await query.answer(f"Ошибка при чтении: {str(e)}", show_alert=True)

        elif data.startswith("files_delete:"):
            path_id = data.split(":", 1)[1]
            path = get_path(path_id)
            if not path:
                await query.answer("Ошибка: путь не найден", show_alert=True)
                return
                
            if await delete_item(path):
                await query.answer("✅ Удалено!")
                # Возврат в родительскую папку
                parent_dir = os.path.dirname(path)
                context.user_data['current_path'] = parent_dir
                await list_directory(update, context, parent_dir)
            else:
                await query.answer("❌ Ошибка при удалении", show_alert=True)

        elif data == "files_back":
            context.user_data['current_path'] = None
            keyboard = [
                [InlineKeyboardButton("📂 Показать файлы", callback_data="files_list")],
                [InlineKeyboardButton("📁 Создать папку", callback_data="files_mkdir")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Выберите действие:", reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Ошибка в handle_button: {str(e)}")
        await query.answer(f"Произошла ошибка: {str(e)}", show_alert=True)

async def files_command(update: Update, context):
    """Команда для запуска файлового менеджера"""
    user_id = update.effective_user.id
    
    if check_spam(user_id, "command"):
        await update.message.reply_text("Подождите немного перед следующей командой!")
        return

    keyboard = [
        [InlineKeyboardButton("📂 Показать файлы", callback_data="files_list")],
        [InlineKeyboardButton("📁 Создать папку", callback_data="files_mkdir")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Файловый менеджер (Windows)\nВыберите действие:",
        reply_markup=reply_markup
    )

async def upload_to_fileio(file_path: str, update: Update, context) -> Optional[str]:
    """Upload file to file.io and return download link"""
    try:
        file_size = os.path.getsize(file_path)
        loading_messages = context.application.bot_data.get('loading_messages', ["Загрузка файла..."])
        progress_message = await update.callback_query.message.reply_text(
            "⏳ Загрузка файла началась...\n"
            f"[{'_' * 10}] 0%\n"
            f"⚡ 0 MB/s\n\n"
            f"💭 {random.choice(loading_messages)}"
        )
        
        start_time = time.time()
        last_update = start_time
        last_size = 0
        message_index = 0
        upload_complete = False
        
        async def update_progress():
            nonlocal last_update, last_size, message_index
            while not upload_complete:
                try:
                    current_time = time.time()
                    elapsed = current_time - start_time
                    
                    if current_time - last_update >= 2:  # Обновляем каждые 2 секунды
                        current_size = last_size + 1024 * 1024  # Примерно увеличиваем на 1MB
                        if current_size > file_size:
                            current_size = file_size
                            
                        progress = min(current_size / file_size * 100, 100)
                        speed = (current_size - last_size) / (current_time - last_update) / 1024 / 1024  # MB/s
                        
                        # Создаем индикатор прогресса
                        filled = int(progress / 10)
                        progress_bar = f"{'█' * filled}{'_' * (10 - filled)}"
                        
                        # Каждые 15 секунд меняем сообщение
                        if int(elapsed) % 15 == 0 and elapsed > 0:
                            message_index = (message_index + 1) % len(loading_messages)
                        
                        await progress_message.edit_text(
                            f"⏳ Загрузка файла: {os.path.basename(file_path)}\n"
                            f"[{progress_bar}] {progress:.1f}%\n"
                            f"⚡ {speed:.1f} MB/s\n\n"
                            f"💭 {loading_messages[message_index]}"
                        )
                        
                        last_size = current_size
                        last_update = current_time
                    
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"Error in progress update: {e}")
                    await asyncio.sleep(1)
        
        # Запускаем обновление прогресса в отдельной задаче
        progress_task = asyncio.create_task(update_progress())
        
        async with aiohttp.ClientSession() as session:
            with open(file_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('file', f)
                data.add_field('expires', '30m')
                
                async with session.post('https://file.io', data=data) as response:
                    result = await response.json()
                    upload_complete = True
                    
                    if response.status == 200:
                        # Дожидаемся завершения задачи прогресса
                        await progress_task
                        
                        # Финальное сообщение
                        await progress_message.edit_text(
                            f"✅ Загрузка завершена!\n"
                            f"[{'█' * 10}] 100%\n"
                            f"📁 Файл: {os.path.basename(file_path)}\n"
                            f"⏱ Время: {int(time.time() - start_time)} сек"
                        )
                        await asyncio.sleep(2)
                        await progress_message.delete()
                        return result.get('link')
        
        upload_complete = True
        await progress_task
        await progress_message.delete()
    except Exception as e:
        logger.error(f"Error uploading to file.io: {e}")
        if 'progress_message' in locals():
            await progress_message.delete()
        if 'progress_task' in locals():
            progress_task.cancel()
    return None

async def handle_file_download(update: Update, context, file_path: str) -> None:
    """Handle file download based on size"""
    try:
        file_size = os.path.getsize(file_path)
        max_file_size = 50 * 1024 * 1024  # Default 50MB
        
        if hasattr(context.application.bot_data, 'config'):
            max_file_size = context.application.bot_data.config.get('max_file_size', max_file_size)
        
        if file_size > max_file_size:
            link = await upload_to_fileio(file_path, update, context)
            if link:
                await update.callback_query.message.reply_text(
                    f"✅ Файл успешно загружен!\n"
                    f"📎 Ссылка для скачивания (действительна 30 минут):\n{link}"
                )
            else:
                await update.callback_query.message.reply_text(
                    "❌ Не удалось загрузить файл. Пожалуйста, попробуйте позже."
                )
        else:
            progress_message = await update.callback_query.message.reply_text(
                "📤 Отправляем файл напрямую...\n"
                f"[{'_' * 10}] 0%"
            )
            
            start_time = time.time()
            try:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=open(file_path, 'rb'),
                    filename=os.path.basename(file_path),
                    progress=lambda current, total: asyncio.create_task(
                        update_progress(progress_message, current, total, start_time)
                    )
                )
            finally:
                await progress_message.delete()
            
    except Exception as e:
        await update.callback_query.message.reply_text(f"❌ Ошибка при отправке файла: {str(e)}")

async def update_progress(message, current, total, start_time):
    """Update progress message for direct file sending"""
    try:
        progress = min(current / total * 100, 100)
        filled = int(progress / 10)
        progress_bar = f"{'█' * filled}{'_' * (10 - filled)}"
        
        elapsed = time.time() - start_time
        speed = current / elapsed / 1024 / 1024  # MB/s
        
        await message.edit_text(
            f"📤 Отправляем файл...\n"
            f"[{progress_bar}] {progress:.1f}%\n"
            f"⚡ {speed:.1f} MB/s"
        )
    except Exception as e:
        logger.error(f"Error updating progress: {e}")

async def launch_file(file_path: str) -> Tuple[bool, str]:
    """Launch a file using the default system application"""
    try:
        os.startfile(file_path)
        return True, "Файл успешно запущен"
    except Exception as e:
        return False, f"Ошибка при запуске файла: {str(e)}"

def register_handlers(app):
    """Регистрация обработчиков модуля"""
    app.add_handler(CommandHandler(COMMAND, files_command))
    app.add_handler(CallbackQueryHandler(handle_button, pattern="^files_"))