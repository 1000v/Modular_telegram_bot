from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackQueryHandler, CommandHandler
import platform
import psutil
import GPUtil
import datetime
import time
import speedtest
import threading
import humanize
import os
import sys
import subprocess

COMMAND = 'sysinfo'
COMMAND_DESCRIPTION = 'Системная информация'

__version__ = "1.0.0"
__doc__ = "Системная информация"
__dependencies__ = ["platform", "psutil", "GPUtil", "speedtest", "threading" "humanize"]  # optional

# Глобальные переменные для хранения информации о сети
network_speed = {"download": 0, "upload": 0}
last_network_update = 0
network_lock = threading.Lock()

def get_size(bytes):
    """Конвертация байтов в человекочитаемый формат"""
    try:
        return humanize.naturalsize(bytes)
    except:
        return f"{bytes} bytes"

def get_system_info():
    """Получение общей информации о системе"""
    try:
        info = {
            "os": f"{platform.system()} {platform.release()}",
            "architecture": platform.machine(),
            "hostname": platform.node(),
            "python": platform.python_version(),
            "boot_time": datetime.datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
        }
        return info
    except Exception as e:
        return {"error": str(e)}

def get_cpu_info():
    """Получение информации о процессоре"""
    try:
        cpu_freq = psutil.cpu_freq()
        cpu_info = {
            "physical_cores": psutil.cpu_count(logical=False),
            "total_cores": psutil.cpu_count(logical=True),
            "total_cpu_usage": f"{psutil.cpu_percent()}%"
        }
        
        # Добавляем частоты только если они доступны
        if cpu_freq:
            cpu_info.update({
                "max_frequency": f"{cpu_freq.max:.2f}MHz",
                "min_frequency": f"{cpu_freq.min:.2f}MHz",
                "current_frequency": f"{cpu_freq.current:.2f}MHz"
            })
        
        # Добавляем информацию по ядрам только если доступна
        try:
            cpu_info["cpu_usage_per_core"] = [f"{percentage:.1f}%" for percentage in psutil.cpu_percent(percpu=True, interval=1)]
        except:
            pass
        
        # Добавляем температуру CPU для Linux
        if platform.system().lower() != 'windows':
            try:
                temps = psutil.sensors_temperatures()
                if 'coretemp' in temps:
                    cpu_temps = temps['coretemp']
                    cpu_info["temperature"] = f"{sum(t.current for t in cpu_temps) / len(cpu_temps):.1f}°C"
            except:
                pass
            
        return cpu_info
    except Exception as e:
        return {"error": str(e)}

def get_memory_info():
    """Получение информации о памяти"""
    try:
        svmem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        memory_info = {
            "total": get_size(svmem.total),
            "available": get_size(svmem.available),
            "used": get_size(svmem.used),
            "percentage": f"{svmem.percent}%"
        }
        
        # Добавляем информацию о swap только если она доступна
        if swap:
            memory_info.update({
                "swap_total": get_size(swap.total),
                "swap_free": get_size(swap.free),
                "swap_used": get_size(swap.used),
                "swap_percentage": f"{swap.percent}%"
            })
            
        return memory_info
    except Exception as e:
        return {"error": str(e)}

def get_gpu_info():
    """Получение информации о видеокарте"""
    try:
        if platform.system().lower() == 'windows':
            # Для Windows используем GPUtil
            gpus = GPUtil.getGPUs()
            gpu_info = []
            for gpu in gpus:
                info = {
                    "name": gpu.name,
                    "load": f"{gpu.load*100:.1f}%",
                    "free_memory": f"{gpu.memoryFree}MB",
                    "used_memory": f"{gpu.memoryUsed}MB",
                    "total_memory": f"{gpu.memoryTotal}MB",
                    "temperature": f"{gpu.temperature} °C"
                }
                gpu_info.append(info)
        else:
            # Для Linux пробуем использовать nvidia-smi
            try:
                result = subprocess.run(['nvidia-smi', '--query-gpu=name,temperature.gpu,memory.total,memory.used,memory.free,utilization.gpu', '--format=csv,noheader,nounits'], 
                                     capture_output=True, text=True)
                if result.returncode == 0:
                    gpu_info = []
                    for line in result.stdout.strip().split('\n'):
                        name, temp, total, used, free, load = line.split(', ')
                        info = {
                            "name": name,
                            "load": f"{load}%",
                            "free_memory": f"{free}MB",
                            "used_memory": f"{used}MB",
                            "total_memory": f"{total}MB",
                            "temperature": f"{temp} °C"
                        }
                        gpu_info.append(info)
                else:
                    return None
            except:
                return None
        return gpu_info
    except:
        return None

def get_battery_info():
    """Получение информации о батарее"""
    try:
        battery = psutil.sensors_battery()
        if battery:
            if platform.system().lower() == 'windows':
                return {
                    "percentage": f"{battery.percent}%",
                    "power_plugged": "Да" if battery.power_plugged else "Нет",
                    "time_left": str(datetime.timedelta(seconds=battery.secsleft)) if battery.secsleft > 0 else "N/A"
                }
            else:  # Linux
                info = {
                    "percentage": f"{battery.percent}%",
                    "power_plugged": "Да" if battery.power_plugged else "Нет"
                }
                # В Linux secsleft может быть отрицательным при зарядке
                if battery.secsleft > 0:
                    info["time_left"] = str(datetime.timedelta(seconds=battery.secsleft))
                elif battery.power_plugged:
                    info["status"] = "Заряжается"
                return info
        return None
    except:
        return None

def get_network_info():
    """Получение информации о сети"""
    try:
        net_io = psutil.net_io_counters()
        return {
            "bytes_sent": get_size(net_io.bytes_sent),
            "bytes_received": get_size(net_io.bytes_recv),
            "packets_sent": net_io.packets_sent,
            "packets_received": net_io.packets_recv,
        }
    except Exception as e:
        return {"error": str(e)}

def format_info_message(title, info_dict):
    """Форматирование информации для отправки"""
    if not info_dict:
        return f" {title}:\nИнформация недоступна"
        
    message = f" {title}:\n\n"
    for key, value in info_dict.items():
        if isinstance(value, list):
            message += f" {key}:\n"
            for item in value:
                if isinstance(item, dict):
                    message += "  " + "\n  ".join(f"{k}: {v}" for k, v in item.items()) + "\n"
                else:
                    message += f"  - {item}\n"
        else:
            message += f" {key}: {value}\n"
    return message

def restart_bot():
    """Перезапуск бота"""
    try:
        python = sys.executable
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'main.py'))
        subprocess.Popen([python, script_path])
        os._exit(0)  # Завершаем текущий процесс
    except Exception as e:
        return f"Ошибка при перезапуске: {str(e)}"

def stop_bot():
    """Полное выключение бота"""
    try:
        os._exit(0)
    except Exception as e:
        return f"Ошибка при выключении бота: {str(e)}"

def system_power_control(action):
    """Управление питанием системы"""
    try:
        if platform.system().lower() == 'windows':
            if action == "shutdown":
                subprocess.run(["shutdown", "/s", "/t", "1"])
                return "Выключение системы..."
            elif action == "restart":
                subprocess.run(["shutdown", "/r", "/t", "1"])
                return "Перезагрузка системы..."
        else:  # Linux
            if action == "shutdown":
                subprocess.run(["sudo", "shutdown", "-h", "now"])
                return "Выключение системы..."
            elif action == "restart":
                subprocess.run(["sudo", "reboot"])
                return "Перезагрузка системы..."
        return "Неизвестная команда"
    except Exception as e:
        return f"Ошибка: {str(e)}"

def get_all_system_info():
    """Получение всей системной информации в одном сообщении"""
    try:
        sys_info = get_system_info()
        cpu_info = get_cpu_info()
        memory_info = get_memory_info()
        gpu_info = get_gpu_info()
        battery_info = get_battery_info()
        
        message = "📊 *Системная информация*\n\n"
        
        # Система
        message += "*🖥️ Система:*\n"
        message += f"• ОС: {sys_info['os']}\n"
        message += f"• Архитектура: {sys_info['architecture']}\n"
        message += f"• Имя компьютера: {sys_info['hostname']}\n"
        message += f"• Python: {sys_info['python']}\n"
        message += f"• Время работы: {sys_info['boot_time']}\n\n"
        
        # Процессор
        message += "*💻 Процессор:*\n"
        message += f"• Физические ядра: {cpu_info['physical_cores']}\n"
        message += f"• Всего ядер: {cpu_info['total_cores']}\n"
        message += f"• Текущая частота: {cpu_info.get('current_frequency', 'N/A')}\n"
        message += f"• Загрузка: {cpu_info['total_cpu_usage']}\n\n"
        
        # Память
        message += "*💾 Память:*\n"
        message += f"• Всего: {memory_info['total']}\n"
        message += f"• Доступно: {memory_info['available']}\n"
        message += f"• Использовано: {memory_info['used']} ({memory_info['percentage']})\n"
        if 'swap_total' in memory_info:
            message += f"• Swap: {memory_info['swap_used']}/{memory_info['swap_total']} ({memory_info['swap_percentage']})\n\n"
        
        # Видеокарта
        if gpu_info and not isinstance(gpu_info, dict):
            message += "*🎮 Видеокарта:*\n"
            for gpu in gpu_info:
                message += f"• Имя: {gpu['name']}\n"
                message += f"• Загрузка: {gpu['load']}\n"
                message += f"• Память: {gpu['used_memory']}/{gpu['total_memory']}\n\n"
        
        # Батарея
        if battery_info and battery_info.get('present', False):
            message += "*🔋 Батарея:*\n"
            message += f"• Заряд: {battery_info['percentage']}%\n"
            message += f"• Статус: {battery_info.get('status', 'Нет данных')}\n"
            if 'time_left' in battery_info:
                message += f"• Осталось: {battery_info['time_left']}\n\n"
        
        return message.strip()
    except Exception as e:
        return f"Ошибка при получении информации: {str(e)}"

async def show_sysinfo_menu(update: Update, context):
    """Показать меню системной информации"""
    keyboard = [
        [InlineKeyboardButton("Показать информацию", callback_data="sysinfo_all")],
        [
            InlineKeyboardButton("🔄 Перезапустить бота", callback_data="bot_restart"),
            InlineKeyboardButton("⛔️ Выключить бота", callback_data="bot_stop")
        ],
        [
            InlineKeyboardButton("🔌 Выключить ПК", callback_data="system_shutdown"),
            InlineKeyboardButton("🔄 Перезагрузить ПК", callback_data="system_restart")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)

async def handle_callback(update: Update, context):
    """Обработчик callback запросов"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "sysinfo_all":
        info_message = get_all_system_info()
        await query.edit_message_text(text=info_message, parse_mode='Markdown')
    elif query.data == "bot_restart":
        await query.edit_message_text(text="Перезапуск бота...")
        restart_bot()
    elif query.data == "bot_stop":
        await query.edit_message_text(text="Выключение бота...")
        stop_bot()
    elif query.data == "system_shutdown":
        await query.edit_message_text(text=system_power_control("shutdown"))
    elif query.data == "system_restart":
        await query.edit_message_text(text=system_power_control("restart"))

async def sysinfo_command(update: Update, context):
    """Обработчик команды системной информации"""
    await show_sysinfo_menu(update, context)

def register_handlers(application):
    """Регистрация обработчиков"""
    application.add_handler(CommandHandler(COMMAND, sysinfo_command))
    application.add_handler(CallbackQueryHandler(handle_callback, pattern="^(sysinfo_|bot_|system_)"))