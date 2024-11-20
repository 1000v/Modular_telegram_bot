from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import NetworkError, TimedOut
import json
import logging
import os
import importlib
import inspect
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
import random

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальный пул потоков
thread_pool = ThreadPoolExecutor(max_workers=4)

# Забавные сообщения во время загрузки
LOADING_MESSAGES = [
    "Обучаем хомяков бегать быстрее для ускорения загрузки... 🐹",
    "Собираем потерянные байты в углах интернета... 🧹",
    "Убеждаем сервер, что это не так уж и много данных... 🤔",
    "Превращаем ваш файл в цифровых голубей... 🕊️",
    "Загружаем файл со скоростью одной бабушки в час... 👵",
    "Пинаем сервер, чтобы он работал быстрее... 🦶",
    "Раскладываем биты по полочкам... 📚",
    "Готовим цифровой телепорт... 🌀",
    "Загрузка идёт со скоростью света... в вакууме... в желе... 🌟",
    "Уговариваем интернет не тормозить... 🐌",
    "Ищем короткий путь через кротовую нору... 🕳️",
    "Файл решил устроить себе перерыв на кофе... ☕",
    "Загружаем со скоростью одного пикселя в минуту... 🐢",
    "Отправляем почтовых голубей с вашими данными... 🕊️",
    "Подключаемся к матрице... 💊",
    "А зачем мы это делаем...?... 🤷‍♀️",
    "А я знаю что ты ...",
    "Проверка на присутствие Главнюка",
]

# Command settings
COMMAND = "start"
COMMAND_DESCRIPTION = "Начать работу с ботом"

class TelegramBot:
    def __init__(self):
        # Загрузка конфигурации
        with open('config.json', 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # Инициализация бота с настройками повторных попыток
        self.app = Application.builder().token(self.config['bot_token'])\
            .connect_timeout(30)\
            .read_timeout(30)\
            .write_timeout(30)\
            .pool_timeout(30)\
            .build()
            
        # Store config in bot_data for access from modules
        self.app.bot_data['config'] = self.config
        self.app.bot_data['loading_messages'] = LOADING_MESSAGES
        
        # Хранилище модулей
        self.modules = {}
        
        # Загрузка модулей
        self.load_modules()
        
    def check_user_access(self, user_id):
        """Проверка доступа пользователя"""
        return str(user_id) in self.config['allowed_users']

    async def error_handler(self, update, context):
        """Обработка ошибок"""
        try:
            if isinstance(context.error, (NetworkError, TimedOut)):
                # Ошибки сети - пробуем повторить через некоторое время
                logger.warning(f"Ошибка сети: {context.error}. Повторная попытка через 5 секунд...")
                await asyncio.sleep(5)
                return
            
            logger.error(f'Update {update} вызвал ошибку {context.error}')
            
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "Произошла ошибка при выполнении команды. Попробуйте позже."
                )
        except Exception as e:
            logger.error(f"Ошибка в обработчике ошибок: {e}")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        user_name = user.first_name
        
        # Получаем список всех файлов в директории modules
        module_dir = os.path.join(os.path.dirname(__file__), 'modules')
        module_files = [f[:-3] for f in os.listdir(module_dir) 
                       if f.endswith('.py') and not f.startswith('__')]
        
        # Собираем команды из всех модулей
        commands = []
        for module_name in module_files:
            try:
                module = __import__(f'modules.{module_name}', fromlist=['COMMAND', 'COMMAND_DESCRIPTION'])
                if hasattr(module, 'COMMAND') and hasattr(module, 'COMMAND_DESCRIPTION'):
                    commands.append(f"/{module.COMMAND} - {module.COMMAND_DESCRIPTION}")
            except (ImportError, AttributeError) as e:
                logger.debug(f"Модуль {module_name} пропущен: {e}")
        
        # Добавляем системные команды
        commands.append(f"/{COMMAND} - {COMMAND_DESCRIPTION}")
        
        welcome_message = (
            f"👋 Привет, {user_name}!\n\n"
            "🌟 Добро пожаловать в многофункционального бота!\n\n"
            "📋 Доступные команды:\n\n"
            f"{chr(10).join(commands)}\n\n"
            "🚀 Приятного использования!"
        )
        
        await update.message.reply_text(welcome_message)

    async def button_handler(self, update: Update, context):
        """Обработчик нажатий на кнопки"""
        try:
            query = update.callback_query
            await query.answer()

            if query.data.startswith("module_"):
                command = query.data.replace("module_", "")
                # Находим соответствующий модуль
                for module in self.modules.values():
                    if hasattr(module, 'COMMAND') and module.COMMAND == command:
                        try:
                            if hasattr(module, 'handle_button'):
                                await module.handle_button(update, context)
                            else:
                                await query.message.reply_text(
                                    f"Используйте /{command} для запуска этой функции"
                                )
                        except Exception as e:
                            logger.error(f"Ошибка при обработке кнопки модуля {command}: {str(e)}")
                            await query.message.reply_text(
                                "Произошла ошибка при обработке команды. Попробуйте еще раз."
                            )
        except Exception as e:
            logger.error(f"Ошибка в button_handler: {str(e)}")

    def load_modules(self):
        """Загрузка всех модулей из директории modules"""
        modules_dir = 'modules'
        if not os.path.exists(modules_dir):
            os.makedirs(modules_dir)
            return

        # Перебираем все файлы в директории modules
        for filename in os.listdir(modules_dir):
            if filename.endswith('.py') and not filename.startswith('__'):
                module_name = filename[:-3]
                try:
                    # Импортируем модуль
                    module = importlib.import_module(f'modules.{module_name}')
                    
                    # Проверяем наличие необходимых атрибутов
                    if all(hasattr(module, attr) for attr in ['COMMAND', 'COMMAND_DESCRIPTION']):
                        self.modules[module_name] = module
                        logger.info(f'Загружен модуль: {module_name}')
                    else:
                        logger.warning(f'Модуль {module_name} пропущен: отсутствуют необходимые атрибуты')
                except Exception as e:
                    logger.error(f'Ошибка при загрузке модуля {module_name}: {str(e)}')

    def run(self):
        """Запуск бота"""
        # Регистрация базовых обработчиков
        self.app.add_handler(CommandHandler(COMMAND, self.start))
        self.app.add_handler(CallbackQueryHandler(self.button_handler, pattern="^module_"))
        self.app.add_error_handler(self.error_handler)
        
        # Регистрация обработчиков из модулей
        for module_name, module in self.modules.items():
            if hasattr(module, 'register_handlers'):
                module.register_handlers(self.app)
            else:
                # Если нет метода register_handlers, ищем корутины и регистрируем их как команды
                for name, obj in inspect.getmembers(module):
                    if inspect.iscoroutinefunction(obj) and name.endswith('_command'):
                        command = getattr(module, 'COMMAND', name.replace('_command', ''))
                        self.app.add_handler(CommandHandler(command, obj))
                        logger.info(f'Зарегистрирована команда /{command} из модуля {module_name}')

        # Запуск бота с настройками повторных попыток
        logger.info("Бот запущен")
        self.app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            pool_timeout=30,
            read_timeout=30,
            connect_timeout=30,
            write_timeout=30
        )

if __name__ == '__main__':
    bot = TelegramBot()
    bot.run()