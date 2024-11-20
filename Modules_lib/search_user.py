from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CommandHandler, CallbackQueryHandler
import requests
import base64
import logging
import os

logger = logging.getLogger(__name__)

COMMAND = 'search'
COMMAND_DESCRIPTION = 'Поиск информации по номеру телефона'

__version__ = "1.0.0"
__doc__ = "Поиск информации по номеру телефона"
__dependencies__ = ["base64", "requests"]  # optional

# ProbivAPI secret key - замените на ваш ключ
PROBIVAPI_KEY = "e45d3b64-585e-4e1d-9f42-ab9f5e7dddc4"

def get_session():
    """Создает сессию с учетом прокси на PythonAnywhere"""
    # Определяем, работаем ли мы на PythonAnywhere
    is_pythonanywhere = os.environ.get('PYTHONANYWHERE_SITE', False)
    
    if is_pythonanywhere:
        # Настройки прокси PythonAnywhere
        proxies = {
            'http': 'http://proxy.server:3128',
            'https': 'http://proxy.server:3128'
        }
        session = requests.Session()
        session.proxies = proxies
        return session
    else:
        return requests.Session()

async def search_by_phone(phone):
    """Поиск информации по номеру телефона через ProbivAPI"""
    url = f"https://probivapi.com/api/phone/info/{phone}"
    pic_url = f"https://probivapi.com/api/phone/pic/{phone}"
    
    headers = {
        "X-Auth": PROBIVAPI_KEY
    }
    
    try:
        session = get_session()
        response = session.get(url, headers=headers)
        json_response = response.json()
        
        # Получаем данные из разных API
        callapp_data = json_response.get('callapp', {})
        callapp_api_name = callapp_data.get('name', 'Не найдено')
        callapp_emails = ', '.join([email.get('email') for email in callapp_data.get('emails', [])])
        callapp_websites = ', '.join([site.get('websiteUrl') for site in callapp_data.get('websites', [])])
        callapp_addresses = ', '.join([addr.get('street') for addr in callapp_data.get('addresses', [])])
        
        eyecon_api_name = json_response.get('eyecon', 'Не найдено')
        viewcaller_name_list = [tag.get('name', 'Не найдено') for tag in json_response.get('viewcaller', [])]
        viewcaller_api_name = ', '.join(viewcaller_name_list)
        
        result = f"""┏ ✅ Информация по номеру {phone}
┣ 📱 ФИО (CallApp): {callapp_api_name}
┣ 📧 Email: {callapp_emails}
┣ 🌐 Сайты: {callapp_websites}
┣ 🏠 Адреса: {callapp_addresses}
┣ 🌐 ФИО (EyeCon): {eyecon_api_name}
┣ 🔎 ФИО (ViewCaller): {viewcaller_api_name}"""
        
        return result
    except Exception as e:
        logger.error(f"Ошибка при поиске: {str(e)}")
        return f"Ошибка при поиске: {str(e)}"

async def search_command(update: Update, context):
    """Обработчик команды /search"""
    if not context.args:
        keyboard = [
            [InlineKeyboardButton("Поиск по номеру", callback_data="search_phone")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Для поиска используйте команду:\n"
            "/search +79XXXXXXXXX",
            reply_markup=reply_markup
        )
        return

    phone = context.args[0]
    result = await search_by_phone(phone)
    await update.message.reply_text(result)

async def button_callback(update: Update, context):
    """Обработчик нажатия кнопки модуля"""
    query = update.callback_query
    await query.answer()

    if query.data == "search_phone":
        await query.message.edit_text(
            "Для поиска информации отправьте команду:\n"
            "/search +79XXXXXXXXX"
        )

def register_handlers(app):
    """Регистрация обработчиков модуля"""
    app.add_handler(CommandHandler(COMMAND, search_command))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^search_"))
    logger.info(f'Зарегистрированы обработчики для модуля {COMMAND}')
