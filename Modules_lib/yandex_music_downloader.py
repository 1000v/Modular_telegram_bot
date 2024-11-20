import os
import requests
from yandex_music import Client
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, USLT
import logging
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaAudio
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# Command settings
COMMAND = 'music'
COMMAND_DESCRIPTION = 'Скачать музыку из Яндекс.Музыки'

__version__ = "1.0.0"
__doc__ = "Скачать музыку из Яндекс.Музыки"
__dependencies__ = ["yandex_music", "mutagen"]  # optional

# Настройка логирования
DOWNLOAD_FOLDER = os.path.join('music')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

file_handler = logging.FileHandler(os.path.join(DOWNLOAD_FOLDER, 'download_log.txt'), encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# Инициализация клиента Яндекс.Музыки
client = None

def init_client(token):
    global client
    if client is None:
        client = Client(token).init()

def sanitize_filename(filename):
    return re.sub(r'[<>:"/\\|?*]', '_', filename)

def get_best_mp3_format(formats, quality='Оптимально'):
    """Получение лучшего доступного формата MP3"""
    if not formats:
        return None
        
    mp3_formats = [fmt for fmt in formats if fmt.codec == 'mp3']
    if not mp3_formats:
        return None

    if quality == 'Lossless':
        quality = 'Оптимально'  # Lossless не доступен для mp3

    if quality == 'Оптимально':
        return max(mp3_formats, key=lambda x: x.bitrate_in_kbps)
    elif quality == 'Экономия':
        return min(mp3_formats, key=lambda x: x.bitrate_in_kbps)
    return mp3_formats[0]

def is_mp3_corrupted(filename):
    """Проверка целостности MP3 файла"""
    try:
        audio = MP3(filename, ID3=ID3)
        audio.pprint()  # Проверка чтения файла
        return False
    except Exception as e:
        logger.error(f"Файл {filename} поврежден: {e}")
        return True

async def download_track(track_info, message, context: ContextTypes.DEFAULT_TYPE):
    """Загрузка трека"""
    try:
        track_title = sanitize_filename(track_info.title)
        artist_name = sanitize_filename(track_info.artists[0].name)
        
        folder_path = os.path.join(DOWNLOAD_FOLDER, str(message.chat.id))
        os.makedirs(folder_path, exist_ok=True)
        filename = os.path.join(folder_path, f"{artist_name} - {track_title}.mp3")
        
        await message.edit_text(f"⏳ Получаю информацию о треке: {artist_name} - {track_title}")
        
        # Получаем информацию о загрузке
        try:
            download_info = track_info.get_download_info()
        except Exception as e:
            logger.error(f"Ошибка при получении информации о загрузке: {e}")
            download_info = None
            
        if not download_info:
            # Пробуем альтернативный способ получения информации
            try:
                download_info = await context.bot.loop.run_in_executor(
                    None, 
                    lambda: client.tracks_download_info(track_info.id)
                )
            except Exception as e:
                logger.error(f"Ошибка при альтернативном получении информации о загрузке: {e}")
                await message.edit_text(f"❌ Не удалось получить информацию для загрузки трека {track_title}")
                return None
        
        if not download_info:
            await message.edit_text(f"❌ Не удалось найти информацию для загрузки трека {track_title}")
            return None
        
        # Если download_info - это список, используем его, иначе создаем список из одного элемента
        if not isinstance(download_info, list):
            download_info = [download_info]
            
        selected_format = get_best_mp3_format(download_info)
        if not selected_format:
            await message.edit_text(f"❌ Не удалось найти подходящий формат для трека {track_title}")
            return None
        
        # Загружаем трек
        await message.edit_text(f"⏳ Загружаю: {artist_name} - {track_title}")
        
        try:
            # Пробуем прямую загрузку через API
            selected_format.download(filename)
        except Exception as e:
            logger.error(f"Ошибка при прямой загрузке трека {track_title}: {e}")
            try:
                # Пробуем альтернативную загрузку через URL
                url = selected_format.get_direct_link()
                response = requests.get(url)
                with open(filename, 'wb') as f:
                    f.write(response.content)
            except Exception as e2:
                logger.error(f"Ошибка при альтернативной загрузке трека {track_title}: {e2}")
                await message.edit_text(f"❌ Ошибка при загрузке трека {track_title}")
                return None

        # Проверяем целостность файла
        if is_mp3_corrupted(filename):
            os.remove(filename)
            await message.edit_text(f"❌ Загруженный файл поврежден: {track_title}")
            return None
        
        # Добавляем метаданные
        try:
            audio = MP3(filename, ID3=ID3)
            if audio.tags is None:
                audio.add_tags()
            
            audio.tags.add(TIT2(encoding=3, text=track_title))
            audio.tags.add(TPE1(encoding=3, text=artist_name))
            
            if track_info.albums:
                audio.tags.add(TALB(encoding=3, text=track_info.albums[0].title))
            
            # Загружаем обложку
            if track_info.cover_uri:
                cover_url = f"https://{track_info.cover_uri.replace('%%', '1000x1000')}"
                cover_data = requests.get(cover_url).content
                audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=cover_data))
            
            # Добавляем текст песни, если есть
            try:
                if track_info.lyrics:
                    audio.tags.add(USLT(encoding=3, lang='eng', desc='', text=track_info.lyrics.full_lyrics))
            except AttributeError:
                pass
            
            audio.save()
            
            # Отправляем файл в Telegram
            with open(filename, 'rb') as audio_file:
                await message.edit_text(f"⬆️ Отправляю: {artist_name} - {track_title}")
                await context.bot.send_audio(
                    chat_id=message.chat.id,
                    audio=audio_file,
                    title=track_title,
                    performer=artist_name,
                    caption=f"🎵 {artist_name} - {track_title}"
                )
            
            # Удаляем локальный файл
            os.remove(filename)
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при обработке файла {filename}: {e}")
            if os.path.exists(filename):
                os.remove(filename)
            await message.edit_text(f"❌ Ошибка при обработке трека {track_title}")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка при загрузке трека {track_title}: {e}")
        await message.edit_text(f"❌ Ошибка при загрузке трека {track_title}")
        if os.path.exists(filename):
            os.remove(filename)
        return None

async def process_music_url(url: str, message, context: ContextTypes.DEFAULT_TYPE):
    """Обработка URL из Яндекс.Музыки"""
    try:
        # Убедимся, что клиент инициализирован
        if client is None:
            token = context.bot_data['config'].get('yandex_music_token')
            if not token:
                await message.edit_text("❌ Отсутствует токен Яндекс.Музыки в конфигурации")
                return None
            init_client(token)

        # Обработка отдельного трека
        if 'track/' in url:
            track_id = url.split('track/')[-1].split('?')[0]
            track = client.tracks([track_id])[0]
            return await download_track(track, message, context)
            
        # Обработка альбома
        elif 'album/' in url:
            album_id = url.split('album/')[-1].split('?')[0]
            album = client.albums_with_tracks(album_id)
            total_tracks = len(album.volumes[0])
            
            # Обновляем сообщение с информацией об альбоме
            await message.edit_text(
                f"📀 Альбом: {album.title}\n"
                f"👤 Исполнитель: {album.artists[0].name}\n"
                f"💿 Треков: {total_tracks}\n\n"
                "⏳ Начинаю загрузку..."
            )
            
            # Загружаем каждый трек
            success_count = 0
            for i, track in enumerate(album.volumes[0], 1):
                status_msg = await context.bot.send_message(
                    chat_id=message.chat.id,
                    text=f"⏳ Загрузка трека {i}/{total_tracks}..."
                )
                if await download_track(track, status_msg, context):
                    success_count += 1
                await status_msg.delete()
            
            # Итоговое сообщение
            await message.edit_text(
                f"✅ Загрузка альбома завершена\n"
                f"📀 {album.title}\n"
                f"✨ Успешно загружено: {success_count}/{total_tracks}"
            )
            return True
            
        # Обработка плейлиста
        elif 'playlist' in url or '/playlists/' in url:
            # Извлекаем user_id и playlist_id из URL
            try:
                # Разбираем URL на части
                parts = url.replace('?utm_medium=copy_link', '').split('/')
                
                # Ищем ID плейлиста (последнее число в URL)
                playlist_id = None
                for part in reversed(parts):
                    if part.isdigit():
                        playlist_id = part
                        break
                
                if not playlist_id:
                    await message.edit_text("❌ Не удалось определить ID плейлиста")
                    return None
                
                # Ищем username пользователя
                user_id = None
                for i, part in enumerate(parts):
                    if part == 'users':
                        user_id = parts[i + 1]
                        break
                
                if not user_id:
                    await message.edit_text("❌ Не удалось определить ID пользователя")
                    return None
                
                # Получаем информацию о плейлисте
                playlist = client.users_playlists(playlist_id, user_id)
                total_tracks = len(playlist.tracks)
                
                # Обновляем сообщение с информацией о плейлисте
                await message.edit_text(
                    f"📝 Плейлист: {playlist.title}\n"
                    f"👤 Владелец: {playlist.owner.name}\n"
                    f"🎵 Треков: {total_tracks}\n\n"
                    "⏳ Начинаю загрузку..."
                )
                
                # Загружаем каждый трек
                success_count = 0
                for i, track_short in enumerate(playlist.tracks, 1):
                    status_msg = await context.bot.send_message(
                        chat_id=message.chat.id,
                        text=f"⏳ Загрузка трека {i}/{total_tracks}..."
                    )
                    if await download_track(track_short.track, status_msg, context):
                        success_count += 1
                    await status_msg.delete()
                
                # Итоговое сообщение
                await message.edit_text(
                    f"✅ Загрузка плейлиста завершена\n"
                    f"📝 {playlist.title}\n"
                    f"✨ Успешно загружено: {success_count}/{total_tracks}"
                )
                return True
                
            except Exception as e:
                logger.error(f"Ошибка при обработке URL плейлиста: {e}")
                await message.edit_text(
                    "❌ Ошибка при обработке ссылки на плейлист\n"
                    "Убедитесь, что ссылка имеет формат:\n"
                    "https://music.yandex.ru/users/USERNAME/playlists/ID"
                )
                return None
            
        else:
            await message.edit_text(
                "❌ Неподдерживаемый формат ссылки\n\n"
                "Поддерживаются ссылки:\n"
                "• На трек: https://music.yandex.ru/album/123456/track/123456\n"
                "• На альбом: https://music.yandex.ru/album/123456\n"
                "• На плейлист: https://music.yandex.ru/users/username/playlists/123456"
            )
            return None
            
    except Exception as e:
        logger.error(f"Ошибка при обработке URL {url}: {e}")
        await message.edit_text(f"❌ Ошибка при обработке ссылки: {str(e)}")
        return None

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатия кнопок"""
    query = update.callback_query
    data = query.data
    
    if data == "music_back":
        keyboard = [
            [InlineKeyboardButton("💾 Скачать по ссылке", callback_data="music_download")],
            [InlineKeyboardButton("ℹ️ Помощь", callback_data="music_help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(
            "🎵 Яндекс.Музыка Downloader\n\n"
            "Выберите действие:",
            reply_markup=reply_markup
        )
    
    elif data == "music_download":
        await query.message.edit_text(
            "🔗 Отправьте ссылку на трек, альбом или плейлист из Яндекс.Музыки"
        )
        context.user_data['expecting_url'] = True
    
    elif data == "music_help":
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="music_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(
            "ℹ️ Помощь\n\n"
            "1. Нажмите 'Скачать по ссылке'\n"
            "2. Отправьте ссылку на музыку из Яндекс.Музыки\n"
            "3. Поддерживаются ссылки на:\n"
            "   • Отдельные треки\n"
            "   • Альбомы\n"
            "   • Плейлисты\n\n"
            "Примеры ссылок:\n"
            "• https://music.yandex.ru/album/123456/track/123456\n"
            "• https://music.yandex.ru/album/123456\n"
            "• https://music.yandex.ru/users/username/playlists/123456",
            reply_markup=reply_markup
        )

async def music_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /music"""
    keyboard = [
        [InlineKeyboardButton("💾 Скачать по ссылке", callback_data="music_download")],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="music_help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎵 Яндекс.Музыка Downloader\n\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    if context.user_data.get('expecting_url'):
        url = update.message.text
        if 'music.yandex.ru' in url:
            status_message = await update.message.reply_text("⏳ Обрабатываю ссылку...")
            await process_music_url(url, status_message, context)
            context.user_data['expecting_url'] = False
        else:
            await update.message.reply_text("❌ Это не похоже на ссылку из Яндекс.Музыки")

def register_handlers(app):
    """Регистрация обработчиков модуля"""
    app.add_handler(CommandHandler(COMMAND, music_command))
    app.add_handler(CallbackQueryHandler(handle_button, pattern="^music_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))