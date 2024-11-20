from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CommandHandler, CallbackQueryHandler
import os
import pwd
import grp
import shutil
from datetime import datetime
import asyncio
import aiohttp
import time
import random
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

COMMAND = 'files'
COMMAND_DESCRIPTION = 'Файловый менеджер (Linux)'

__version__ = "1.0.0"
__doc__ = "Файловый менеджер (Linux)"
__dependencies__ = ["pwdpy", "shutil", "aiohttp"]  # optional

# Глобальный словарь для хранения путей
path_store = {}

def generate_path_id(path: str):
    """Генерирует короткий ID для пути"""
    import hashlib
    return hashlib.md5(path.encode()).hexdigest()[:8]

def store_path(path: str):
    """Сохраняет путь и возвращает его ID"""
    path_id = generate_path_id(path)
    path_store[path_id] = path
    return path_id

def get_path(path_id: str):
    """Получает путь по его ID"""
    return path_store.get(path_id)

def format_size(size: int):
    """Форматирование размера файла"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"

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

async def launch_file(file_path: str) -> Tuple[bool, str]:
    """Launch a file using xdg-open"""
    try:
        os.system(f"xdg-open '{file_path}'")
        return True, "Файл успешно запущен"
    except Exception as e:
        return False, f"Ошибка при запуске файла: {str(e)}"

async def handle_button(update: Update, context):
    """Обработчик нажатия кнопки модуля"""
    query = update.callback_query
    data = query.data

    if data == "files_list":
        current_path = context.user_data.get('current_path', '/')
        await list_directory(update, context, current_path)
        
    elif data.startswith("files_open:"):
        path_id = data.split(":", 1)[1]
        path = get_path(path_id)
        if not path:
            await query.answer("Ошибка: путь не найден", show_alert=True)
            return
            
        context.user_data['current_path'] = path
        
        if os.path.isfile(path):
            # Информация о файле
            stats = os.stat(path)
            owner = pwd.getpwuid(stats.st_uid).pw_name
            group = grp.getgrgid(stats.st_gid).gr_name
            perms = oct(stats.st_mode)[-3:]
            
            text = (
                f"📄 Файл: {os.path.basename(path)}\n"
                f"📦 Размер: {format_size(stats.st_size)}\n"
                f"👤 Владелец: {owner}\n"
                f"👥 Группа: {group}\n"
                f"🔒 Права: {perms}\n"
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

async def list_directory(update: Update, context, path=None):
    """Отображение содержимого директории"""
    if path is None:
        path = '/'
    
    try:
        items = os.listdir(path)
        keyboard = []
        
        # Сортируем: сначала папки, потом файлы
        dirs = []
        files = []
        for item in items:
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                dirs.append((item, full_path))
            else:
                files.append((item, full_path))
        
        # Добавляем папки
        for name, full_path in sorted(dirs):
            path_id = store_path(full_path)
            keyboard.append([InlineKeyboardButton(
                f"📁 {name}", 
                callback_data=f"files_open:{path_id}"
            )])
        
        # Добавляем файлы
        for name, full_path in sorted(files):
            path_id = store_path(full_path)
            keyboard.append([InlineKeyboardButton(
                f"📄 {name}", 
                callback_data=f"files_open:{path_id}"
            )])
        
        # Добавляем кнопку "Вверх", если мы не в корневой папке
        if path != '/':
            parent_id = store_path(os.path.dirname(path))
            keyboard.append([InlineKeyboardButton(
                "⬆️ Вверх", 
                callback_data=f"files_open:{parent_id}"
            )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.message.edit_text(
                f"📂 Текущая папка: {path}",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                f"📂 Текущая папка: {path}",
                reply_markup=reply_markup
            )
            
    except Exception as e:
        error_message = f"❌ Ошибка при чтении директории: {str(e)}"
        if update.callback_query:
            await update.callback_query.message.edit_text(error_message)
        else:
            await update.message.reply_text(error_message)

async def files_command(update: Update, context):
    """Команда для запуска файлового менеджера"""
    await list_directory(update, context, '/')

def register_handlers(app):
    """Регистрация обработчиков модуля"""
    app.add_handler(CommandHandler(COMMAND, files_command))
    app.add_handler(CallbackQueryHandler(handle_button, pattern="^files_"))
