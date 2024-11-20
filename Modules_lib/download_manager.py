# modules/download_manager.py
from telegram import Update
import aiohttp
import os
from urllib.parse import urlparse, unquote
import re
import mimetypes

COMMAND = 'download'
COMMAND_DESCRIPTION = 'Скачать файл из интернета. Использование: /download <url> [имя_файла]'

__version__ = "1.0.0"
__doc__ = "Скачать файл из интернета"
__dependencies__ = ["aiohttp"]  # optional

def sanitize_filename(filename):
    """Очистка имени файла от недопустимых символов"""
    # Заменяем недопустимые символы на подчеркивание
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Убираем точки в начале имени файла (Windows не любит такие файлы)
    filename = filename.lstrip('.')
    return filename if filename else 'downloaded_file'

def get_filename_from_url(url, content_disposition=None, content_type=None):
    """Получение имени файла из URL или заголовков"""
    filename = None
    
    # Пытаемся получить имя файла из Content-Disposition
    if content_disposition:
        try:
            filename_match = re.search(r'filename=["\'](.*?)["\']', content_disposition)
            if filename_match:
                filename = filename_match.group(1)
        except Exception:
            pass
    
    # Если не удалось получить из заголовка, пробуем из URL
    if not filename:
        parsed_url = urlparse(url)
        path = unquote(parsed_url.path)
        filename = os.path.basename(path)
    
    # Если все еще нет имени файла, используем расширение на основе типа контента
    if not filename and content_type:
        ext = mimetypes.guess_extension(content_type.split(';')[0].strip())
        if ext:
            filename = f'downloaded_file{ext}'
    
    # Если ничего не помогло, используем стандартное имя
    if not filename:
        filename = 'downloaded_file'
    
    return sanitize_filename(filename)

async def download_command(update: Update, context):
    """Модуль для скачивания файлов"""
    user_message = update.message.text.split()
    if len(user_message) < 2:
        await update.message.reply_text(
            "Использование: /download <url> [имя_файла]\n"
            "Например:\n"
            "/download https://example.com/file.pdf\n"
            "/download https://example.com/file.pdf my_file.pdf"
        )
        return
    
    url = user_message[1]
    custom_filename = user_message[2] if len(user_message) > 2 else None
    
    try:
        status_message = await update.message.reply_text("Начинаю загрузку файла...")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    content = await response.read()
                    
                    # Получаем имя файла
                    if custom_filename:
                        filename = sanitize_filename(custom_filename)
                    else:
                        content_disposition = response.headers.get('Content-Disposition')
                        content_type = response.headers.get('Content-Type')
                        filename = get_filename_from_url(url, content_disposition, content_type)
                    
                    # Создаем директорию downloads, если её нет
                    os.makedirs('downloads', exist_ok=True)
                    
                    # Полный путь к файлу
                    filepath = os.path.join('downloads', filename)
                    
                    # Записываем файл
                    with open(filepath, 'wb') as f:
                        f.write(content)
                    
                    # Получаем размер файла в МБ
                    file_size = os.path.getsize(filepath) / (1024 * 1024)
                    
                    await status_message.edit_text(
                        f"✅ Файл успешно загружен\n"
                        f"📁 Имя файла: {filename}\n"
                        f"📊 Размер: {file_size:.2f} МБ\n"
                        f"📂 Путь: {filepath}"
                    )
                else:
                    await status_message.edit_text(
                        f"❌ Ошибка при скачивании\n"
                        f"Статус: {response.status}\n"
                        f"Причина: {response.reason}"
                    )
    except aiohttp.ClientError as e:
        await status_message.edit_text(f"❌ Ошибка сети при скачивании: {str(e)}")
    except Exception as e:
        await status_message.edit_text(f"❌ Ошибка при скачивании: {str(e)}")