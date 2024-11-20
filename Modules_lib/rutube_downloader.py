from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from rutube import Rutube
import os
import asyncio
import time
import random
import re
import aiohttp
import json
import logging

logger = logging.getLogger(__name__)

COMMAND = 'rutube'
COMMAND_DESCRIPTION = 'Скачать видео с Rutube'

__version__ = "1.0.0"
__doc__ = "Скачать видео с Rutube"
__dependencies__ = ["aiohttp", "rutube"]

# Список файловых хостингов
FILE_HOSTS = [
    {
        'name': 'file.io',
        'url': 'https://file.io/',
        'field_name': 'file',
        'link_key': 'link',
        'success_key': 'success'
    },
    {
        'name': 'tmpfiles.org',
        'url': 'https://tmpfiles.org/api/v1/upload',
        'field_name': 'file',
        'link_key': 'data.url',
        'success_key': 'status'
    }
]

# Забавные сообщения во время загрузки
UPLOAD_MESSAGES = [
    "Загружаем видео в облако... ☁️",
    "Пакуем байты в красивую обертку... 🎁",
    "Отправляем видео в путешествие по сети... 🚀",
    "Готовим ссылку для вас... 🔗",
    "Ждем ответа от серверов... 📡",
    "Почти готово... ⌛",
]

# Забавные сообщения во время скачивания
DOWNLOAD_MESSAGES = [
    "🎬 Начинаем загрузку видео...",
    "📥 Скачиваем видео с Rutube...",
    "🎯 Готовим видео в выбранном качестве...",
    "🔄 Конвертируем видео...",
    "📦 Упаковываем видео для вас...",
    "🚀 Запускаем процесс загрузки...",
]

class RutubeDownloader:
    def __init__(self):
        self.user_urls = {}
        self.downloads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'downloads')
        os.makedirs(self.downloads_dir, exist_ok=True)

    async def update_progress(self, message, current, total, start_time, messages):
        """Обновление прогресса загрузки"""
        try:
            progress = current / total * 100
            elapsed = time.time() - start_time
            speed = current / (1024 * 1024 * elapsed) if elapsed > 0 else 0
            eta = int((total - current) / (current / elapsed) if current > 0 else 0)
            
            message_index = int(elapsed / 15) % len(messages)
            status_text = f"{messages[message_index]}\n"
            status_text += f"Прогресс: {progress:.1f}%\n"
            status_text += f"Скорость: {speed:.1f} MB/s\n"
            status_text += f"Осталось: {eta} сек"
            
            await message.edit_text(status_text)
        except Exception as e:
            logger.error(f"Ошибка при обновлении прогресса: {e}")

    async def upload_to_fileio(self, file_path: str, progress_msg, context) -> str:
        """Upload file to file.io and return download link"""
        try:
            file_size = os.path.getsize(file_path)
            start_time = time.time()
            last_update = start_time
            last_size = 0
            upload_complete = False
            message_index = 0
            
            # Обрезаем имя файла до 30 символов (с запасом от лимита в 255)
            filename = os.path.basename(file_path)
            if len(filename) > 50:
                name, ext = os.path.splitext(filename)
                filename = name[:46] + "..." + ext
            
            logger.info(f"Uploading file: {filename}")
            
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
                            
                            # Обновляем индекс сообщения каждые 15 секунд
                            message_index = int(elapsed / 15) % len(UPLOAD_MESSAGES)
                            fun_message = UPLOAD_MESSAGES[message_index]
                            
                            await progress_msg.edit_text(
                                f"⏳ Загрузка файла: {filename}\n"
                                f"[{progress_bar}] {int(progress)}%\n"
                                f"⚡ {speed:.1f} MB/s\n\n"
                                f"💭 {fun_message}"
                            )
                            
                            last_size = current_size
                            last_update = current_time
                        
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        logger.error(f"Error in progress update: {e}")
                        await asyncio.sleep(1)
            
            # Запускаем обновление прогресса в отдельной задаче
            progress_task = asyncio.create_task(update_progress())
            
            # Добавляем user agent и другие заголовки
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Origin': 'https://file.io',
                'Referer': 'https://file.io/'
            }
            
            async with aiohttp.ClientSession(headers=headers) as session:
                with open(file_path, 'rb') as f:
                    data = aiohttp.FormData()
                    data.add_field('file', f, filename=filename)
                    data.add_field('expires', '24h')  # Увеличиваем время жизни файла до 24 часов
                    
                    async with session.post('https://file.io', data=data) as response:
                        result = await response.json()
                        upload_complete = True
                        logger.info(f"File.io response: {result}")
                        
                        if response.status == 200 and result.get('success'):
                            # Дожидаемся завершения задачи прогресса
                            await progress_task
                            
                            # Финальное сообщение
                            await progress_msg.edit_text(
                                f"✅ Загрузка завершена!\n"
                                f"[{'█' * 10}] 100%\n"
                                f"📁 Файл: {filename}\n"
                                f"⏱ Время: {int(time.time() - start_time)} сек"
                            )
                            await asyncio.sleep(2)
                            return result.get('link')
                        else:
                            error_msg = result.get('message', 'Unknown error')
                            logger.error(f"File.io upload failed: {error_msg}")
            
            upload_complete = True
            await progress_task
        except Exception as e:
            logger.error(f"Error uploading to file.io: {e}")
            if 'progress_task' in locals():
                progress_task.cancel()
        return None

    async def send_file(self, file_path: str, message, context):
        """Отправка файла пользователю"""
        try:
            # Сначала пробуем загрузить на file.io
            cloud_link = await self.upload_to_fileio(file_path, message, context)
            
            if cloud_link:
                await message.edit_text(
                    f"✅ Видео успешно загружено!\n\n"
                    f"🔗 Ссылка на скачивание: {cloud_link}\n\n"
                    f"⚠️ Ссылка действительна 24 часа"
                )
                return

            # Если загрузка на облако не удалась, отправляем напрямую
            file_size = os.path.getsize(file_path)
            with open(file_path, 'rb') as video_file:
                await context.bot.send_video(
                    chat_id=message.chat_id,
                    video=video_file,
                    caption="Вот ваше видео!"
                )
            await message.delete()
            
        except Exception as e:
            logger.error(f"Ошибка при отправке файла: {e}")
            await message.edit_text("Произошла ошибка при отправке видео")

    async def download_rutube_video(self, url: str, resolution: str, msg, context, title: str):
        """Скачивание видео"""
        start_time = time.time()
        file_path = None
        
        try:
            rt = Rutube(url)
            
            if resolution == "best":
                video = rt.get_best()
            else:
                video = rt.get_by_resolution(int(resolution))
            
            if not video:
                await msg.edit_text("Не удалось получить видео в выбранном качестве")
                return
            
            safe_title = self.sanitize_filename(title)
            file_path = os.path.join(self.downloads_dir, f"{safe_title}_{resolution}p_{int(time.time())}.mp4")
            
            # Показываем начальное сообщение
            initial_message = "🎬 Начал загружать..."
            current_message = msg.text if msg.text else ""
            
            if current_message != initial_message:
                await msg.edit_text(initial_message)
            await asyncio.sleep(2)  # Ждем 2 секунды
            
            # Выбираем сообщение из DOWNLOAD_MESSAGES, пропуская первое
            download_msg = random.choice(DOWNLOAD_MESSAGES[1:])
            if current_message != download_msg:  # Проверяем, что сообщение отличается
                await msg.edit_text(download_msg)
            
            # Скачиваем видео
            with open(file_path, 'wb') as f:
                video.download(stream=f)
            
            # Отправляем файл пользователю
            await self.send_file(file_path, msg, context)
            
        except Exception as e:
            logger.error(f"Ошибка при скачивании видео: {e}")
            await msg.edit_text("Произошла ошибка при скачивании видео")
        
        finally:
            # Безопасное удаление файла
            if file_path and os.path.exists(file_path):
                try:
                    # Даем небольшую задержку перед удалением
                    await asyncio.sleep(2)
                    os.remove(file_path)
                except Exception as e:
                    logger.error(f"Ошибка при удалении файла {file_path}: {e}")
                    # Планируем повторную попытку удаления через некоторое время
                    asyncio.create_task(self.delayed_file_cleanup(file_path))

    async def delayed_file_cleanup(self, file_path: str, max_attempts: int = 3):
        """Отложенная очистка файла с несколькими попытками"""
        attempt = 0
        while attempt < max_attempts:
            await asyncio.sleep(30)  # Ждем 30 секунд между попытками
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    break
            except Exception as e:
                logger.error(f"Попытка {attempt + 1} удаления файла {file_path} не удалась: {e}")
                attempt += 1

    async def rutube_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /rutube"""
        await update.message.reply_text(
            "Отправьте мне ссылку на видео с Rutube, и я помогу вам его скачать!"
        )

    async def handle_rutube_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик URL от Rutube"""
        message = update.message
        url = message.text.strip()
        
        if not url.startswith(('https://rutube.ru', 'http://rutube.ru')):
            await message.reply_text("Это не похоже на ссылку с Rutube. Пожалуйста, отправьте корректную ссылку.")
            return

        loading_msg = await message.reply_text("Получаю информацию о видео...")
        
        try:
            rt = Rutube(url)
            resolutions = rt.available_resolutions
            
            if not resolutions:
                await loading_msg.edit_text("Не удалось получить информацию о видео")
                return
            
            # Сохраняем URL для последующего использования
            self.user_urls[update.effective_user.id] = {
                'url': url,
                'title': 'video'  # Заголовок будет добавлен при скачивании
            }
            
            # Создаем клавиатуру с доступными разрешениями
            keyboard = []
            for res in sorted(resolutions):
                keyboard.append([
                    InlineKeyboardButton(
                        f"{res}p",
                        callback_data=f"rutube_{res}"
                    )
                ])
            keyboard.append([
                InlineKeyboardButton(
                    "🎯 Лучшее качество",
                    callback_data="rutube_best"
                )
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await loading_msg.edit_text(
                f"🎥 Выберите качество видео:\n\n"
                f"Доступные разрешения: {', '.join(f'{r}p' for r in sorted(resolutions))}",
                reply_markup=reply_markup
            )
        
        except Exception as e:
            logger.error(f"Ошибка при обработке URL: {e}")
            await loading_msg.edit_text("Произошла ошибка при получении информации о видео")

    async def handle_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатия кнопок"""
        query = update.callback_query
        await query.answer()
        
        if not query.data.startswith('rutube_'):
            return
        
        user_id = update.effective_user.id
        if user_id not in self.user_urls:
            await query.edit_message_text("Сессия истекла. Пожалуйста, отправьте ссылку заново.")
            return
        
        url_data = self.user_urls[user_id]
        loading_msg = await query.edit_message_text("🎬 Начал загружать...")
        
        try:
            resolution = query.data.split('_')[1]  # Может быть 'best' или число
            await self.download_rutube_video(
                url_data['url'],
                resolution,
                loading_msg,
                context,
                url_data['title']
            )
        except Exception as e:
            logger.error(f"Ошибка при обработке кнопки: {e}")
            await loading_msg.edit_text("Произошла ошибка при загрузке видео")
        finally:
            # Очищаем данные пользователя
            self.user_urls.pop(user_id, None)

    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений"""
        if update.message and update.message.text:
            if 'rutube.ru' in update.message.text.lower():
                await self.handle_rutube_url(update, context)

    @staticmethod
    def sanitize_filename(filename):
        """Очистка имени файла от недопустимых символов"""
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:196] + ext
        return filename

def register_handlers(app):
    """Регистрация обработчиков модуля"""
    rutube_downloader = RutubeDownloader()
    app.add_handler(CommandHandler(COMMAND, rutube_downloader.rutube_command))
    app.add_handler(CallbackQueryHandler(rutube_downloader.handle_button, pattern='^rutube_'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, rutube_downloader.message_handler))