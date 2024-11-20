import customtkinter as ctk
import json
import os
import subprocess
import shutil
import platform
import tkinter as tk
from tkinter import messagebox, scrolledtext
import requests
import sys
import re
from packaging import version

class ModuleManager:
    def __init__(self, modules_dir, modules_lib_dir):
        self.modules_dir = modules_dir
        self.modules_lib_dir = modules_lib_dir
        self.github_api = "https://api.github.com/repos"
        self.repo_owner = "1000v"
        self.repo_name = "Modular_telegram_bot"
        self.modules_branch = "main"
        self.repo_url = f"https://github.com/{self.repo_owner}/{self.repo_name}"
        
        # Создаем директории если их нет
        os.makedirs(self.modules_dir, exist_ok=True)
        os.makedirs(self.modules_lib_dir, exist_ok=True)

    def get_active_modules(self):
        return [f for f in os.listdir(self.modules_dir) 
                if f.endswith('.py') and not f.startswith('__')]

    def get_available_modules(self):
        return [f for f in os.listdir(self.modules_lib_dir) 
                if f.endswith('.py') and not f.startswith('__')]

    def enable_module(self, module_name):
        if not module_name.endswith('.py'):
            module_name += '.py'
        src = os.path.join(self.modules_lib_dir, module_name)
        dst = os.path.join(self.modules_dir, module_name)
        if os.path.exists(src):
            try:
                shutil.move(src, dst)  # Используем move вместо copy2
                return True
            except Exception as e:
                print(f"Ошибка при включении модуля: {e}")
                return False
        return False

    def disable_module(self, module_name):
        if not module_name.endswith('.py'):
            module_name += '.py'
        src = os.path.join(self.modules_dir, module_name)
        dst = os.path.join(self.modules_lib_dir, module_name)
        if os.path.exists(src):
            try:
                shutil.move(src, dst)  # Используем move вместо remove
                return True
            except Exception as e:
                print(f"Ошибка при отключении модуля: {e}")
                return False
        return False

    def check_for_updates(self):
        """Проверка обновлений из GitHub"""
        try:
            # Получаем последний коммит с GitHub
            response = requests.get(
                f"{self.repo_url}/raw/{self.modules_branch}/version.json"
            )
            if response.status_code == 404:
                # Если version.json не найден, используем информацию о коммитах
                return self.check_updates_by_commits()
            
            online_version = response.json()
            
            # Читаем локальную версию
            try:
                with open("version.json", "r", encoding='utf-8') as f:
                    local_version = json.load(f)
            except FileNotFoundError:
                local_version = {"version": "0.0.0", "changes": []}
            
            if version.parse(online_version["version"]) > version.parse(local_version["version"]):
                return {
                    "has_updates": True,
                    "changes": online_version.get("changes", []),
                    "current_version": local_version["version"],
                    "new_version": online_version["version"]
                }
            return {"has_updates": False, "current_version": local_version["version"]}
            
        except Exception as e:
            print(f"Error checking updates: {e}")
            return None

    def check_updates_by_commits(self):
        """Проверка обновлений через API GitHub"""
        try:
            # Получаем последний коммит
            response = requests.get(
                f"{self.github_api}/{self.repo_owner}/{self.repo_name}/commits/{self.modules_branch}",
                headers={"Accept": "application/vnd.github.v3+json"}
            )
            response.raise_for_status()
            latest_commit = response.json()
            
            # Получаем текущий коммит
            try:
                with open(".git/refs/heads/main", "r") as f:
                    current_commit = f.read().strip()
            except:
                return {
                    "has_updates": True,
                    "changes": ["Первоначальная установка"],
                    "current_version": "0.0.0",
                    "new_version": "1.0.0"
                }
            
            if latest_commit["sha"] != current_commit:
                return {
                    "has_updates": True,
                    "changes": [c["commit"]["message"] for c in response.json()],
                    "current_version": "current",
                    "new_version": "latest"
                }
            return {"has_updates": False, "current_version": "current"}
            
        except Exception as e:
            print(f"Error checking updates by commits: {e}")
            return None

    def update_bot(self):
        """Обновление бота из GitHub"""
        try:
            # Скачиваем основные файлы
            files_to_update = ["main.py", "config.json", "requirements.txt"]
            
            for file in files_to_update:
                response = requests.get(f"{self.repo_url}/raw/{self.modules_branch}/{file}")
                if response.status_code == 200:
                    with open(file, "wb") as f:
                        f.write(response.content)
            
            # Скачиваем version.json если есть
            response = requests.get(f"{self.repo_url}/raw/{self.modules_branch}/version.json")
            if response.status_code == 200:
                with open("version.json", "wb") as f:
                    f.write(response.content)
            
            # Устанавливаем зависимости
            if os.path.exists("requirements.txt"):
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            
            return True
        except Exception as e:
            print(f"Error updating bot: {e}")
            return False

    def get_available_store_modules(self):
        """Получение списка доступных модулей из GitHub"""
        try:
            # Получаем список файлов в директории Modules_lib
            response = requests.get(
                f"{self.github_api}/{self.repo_owner}/{self.repo_name}/contents/Modules_lib",
                headers={"Accept": "application/vnd.github.v3+json"}
            )
            response.raise_for_status()
            
            modules = []
            for item in response.json():
                if item["name"].endswith(".py") and not item["name"].startswith("__"):
                    # Получаем содержимое модуля
                    module_content = requests.get(item["download_url"]).text
                    
                    # Извлекаем метаданные
                    version_match = re.search(r'__version__\s*=\s*["\'](.+?)["\']', module_content)
                    doc_match = re.search(r'__doc__\s*=\s*["\'](.+?)["\']', module_content)
                    dep_match = re.search(r'__dependencies__\s*=\s*\[(.*?)\]', module_content)
                    
                    version = version_match.group(1) if version_match else "1.0.0"
                    description = doc_match.group(1) if doc_match else "Нет описания"
                    dependencies = []
                    if dep_match:
                        dependencies = [dep.strip().strip('"\'') for dep in dep_match.group(1).split(',') if dep.strip()]
                    
                    modules.append({
                        "name": item["name"][:-3],
                        "version": version,
                        "description": description,
                        "dependencies": dependencies,
                        "download_url": item["download_url"]
                    })
            
            return modules
        except Exception as e:
            print(f"Error getting store modules: {e}")
            return []

    def download_module(self, module_url, module_name):
        """Скачивание модуля из GitHub"""
        try:
            # Скачиваем модуль
            response = requests.get(module_url)
            response.raise_for_status()
            
            # Сохраняем в Modules_lib
            module_path = os.path.join(self.modules_lib_dir, f"{module_name}.py")
            with open(module_path, "w", encoding="utf-8") as f:
                f.write(response.text)
            
            # Извлекаем и устанавливаем зависимости
            dep_match = re.search(r'__dependencies__\s*=\s*\[(.*?)\]', response.text)
            if dep_match:
                dependencies = [dep.strip().strip('"\'') for dep in dep_match.group(1).split(',') if dep.strip()]
                for dep in dependencies:
                    try:
                        subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
                    except Exception as e:
                        print(f"Error installing dependency {dep}: {e}")
            
            return True
        except Exception as e:
            print(f"Error downloading module: {e}")
            return False

class BotManager(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title('Telegram Bot Manager')
        self.geometry('1200x700')
        
        # Настройка темы
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Инициализация менеджера модулей
        self.module_manager = ModuleManager("modules", "Modules_lib")
        
        # Проверка наличия config.json
        if not self.check_config_exists():
            self.show_config_form()
        else:
            self.create_gui()
            self.load_config()

    def check_config_exists(self):
        """Проверка наличия файла конфигурации"""
        return os.path.exists('config.json')

    def show_config_form(self):
        """Показать форму для создания config.json"""
        self.config_window = ctk.CTkToplevel(self)
        self.config_window.title('Создание конфигурации')
        self.config_window.geometry('600x800')
        self.config_window.transient(self)
        self.config_window.grab_set()

        # Создаем основной frame с прокруткой
        main_frame = ctk.CTkScrollableFrame(self.config_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)

        # Bot Token
        ctk.CTkLabel(main_frame, text="Bot Token:").pack(pady=5)
        token_entry = ctk.CTkEntry(main_frame, width=500)
        token_entry.pack(pady=5)

        # Yandex Music Token
        ctk.CTkLabel(main_frame, text="Yandex Music Token:").pack(pady=5)
        yandex_token_entry = ctk.CTkEntry(main_frame, width=500)
        yandex_token_entry.pack(pady=5)

        # Allowed Users
        ctk.CTkLabel(main_frame, text="Allowed Users (через запятую):").pack(pady=5)
        allowed_entry = ctk.CTkEntry(main_frame, width=500)
        allowed_entry.pack(pady=5)

        # Download Folder
        ctk.CTkLabel(main_frame, text="Download Folder:").pack(pady=5)
        download_folder_entry = ctk.CTkEntry(main_frame, width=500)
        download_folder_entry.insert(0, "downloads")
        download_folder_entry.pack(pady=5)

        # Max File Size
        ctk.CTkLabel(main_frame, text="Max File Size (bytes):").pack(pady=5)
        max_file_size_entry = ctk.CTkEntry(main_frame, width=500)
        max_file_size_entry.insert(0, "50000000")
        max_file_size_entry.pack(pady=5)

        # Allowed Extensions
        ctk.CTkLabel(main_frame, text="Allowed Extensions (через запятую):").pack(pady=5)
        allowed_ext_entry = ctk.CTkEntry(main_frame, width=500)
        allowed_ext_entry.insert(0, ".txt,.pdf,.jpg,.png")
        allowed_ext_entry.pack(pady=5)

        # Hidden Files
        ctk.CTkLabel(main_frame, text="Hidden Files:").pack(pady=5)

        # System Files
        ctk.CTkLabel(main_frame, text="System Files (через запятую):").pack(pady=5)
        system_files_entry = ctk.CTkEntry(main_frame, width=500)
        system_files_entry.insert(0, ".dll,.sys,.exe,.bin")
        system_files_entry.pack(pady=5)

        # Temporary Files
        ctk.CTkLabel(main_frame, text="Temporary Files (через запятую):").pack(pady=5)
        temp_files_entry = ctk.CTkEntry(main_frame, width=500)
        temp_files_entry.insert(0, ".tmp,.temp,.cache")
        temp_files_entry.pack(pady=5)

        # Hidden Files
        ctk.CTkLabel(main_frame, text="Hidden Files (через запятую):").pack(pady=5)
        hidden_files_entry = ctk.CTkEntry(main_frame, width=500)
        hidden_files_entry.insert(0, ".git,.env,.vscode,.idea")
        hidden_files_entry.pack(pady=5)

        # Backup Files
        ctk.CTkLabel(main_frame, text="Backup Files (через запятую):").pack(pady=5)
        backup_files_entry = ctk.CTkEntry(main_frame, width=500)
        backup_files_entry.insert(0, ".bak,.backup,~")
        backup_files_entry.pack(pady=5)

        def save_config():
            token = token_entry.get().strip()
            yandex_token = yandex_token_entry.get().strip()
            allowed_users = [user.strip() for user in allowed_entry.get().split(',') if user.strip()]
            download_folder = download_folder_entry.get().strip()
            max_file_size = int(max_file_size_entry.get().strip())
            allowed_extensions = [ext.strip() for ext in allowed_ext_entry.get().split(',') if ext.strip()]
            
            # Hidden files
            system_files = [f.strip() for f in system_files_entry.get().split(',') if f.strip()]
            temp_files = [f.strip() for f in temp_files_entry.get().split(',') if f.strip()]
            hidden_files = [f.strip() for f in hidden_files_entry.get().split(',') if f.strip()]
            backup_files = [f.strip() for f in backup_files_entry.get().split(',') if f.strip()]

            if not token:
                messagebox.showerror("Ошибка", "Bot Token обязателен для заполнения!")
                return

            config = {
                "bot_token": token,
                "yandex_music_token": yandex_token,
                "allowed_users": allowed_users,
                "download_folder": download_folder,
                "max_file_size": max_file_size,
                "allowed_extensions": allowed_extensions,
                "hidden_files": {
                    "system": system_files,
                    "temporary": temp_files,
                    "hidden": hidden_files,
                    "backup": backup_files
                }
            }

            try:
                with open('config.json', 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)
                self.config_window.destroy()
                self.create_gui()
                self.load_config()
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить конфигурацию: {str(e)}")

        ctk.CTkButton(main_frame, text="Сохранить", command=save_config).pack(pady=20)

    def create_gui(self):
        # Основной контейнер
        self.main_container = ctk.CTkFrame(self)
        self.main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Левое меню
        self.menu_frame = ctk.CTkFrame(self.main_container, width=200)
        self.menu_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        # Кнопки меню
        menu_items = [
            ("Управление", self.show_control_page),
            ("Модули", self.show_modules_page),
            ("Настройки", self.show_config_page),
            ("Магазин", self.show_store_page),
            ("Обновления", self.show_updates_page)
        ]

        for text, command in menu_items:
            btn = ctk.CTkButton(
                self.menu_frame,
                text=text,
                command=command,
                width=180
            )
            btn.pack(pady=5, padx=10)

        # Основная область контента
        self.content_frame = ctk.CTkFrame(self.main_container)
        self.content_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Создаем страницы
        self.pages = {}
        self.create_control_page()
        self.create_modules_page()
        self.create_config_page()
        self.create_store_page()
        self.create_updates_page()

        # Показываем первую страницу
        self.show_control_page()

    def show_page(self, page_name):
        for page in self.pages.values():
            page.pack_forget()
        self.pages[page_name].pack(fill=tk.BOTH, expand=True)

    def show_control_page(self):
        self.show_page('control')

    def show_modules_page(self):
        self.show_page('modules')
        self.update_module_lists()

    def show_config_page(self):
        self.show_page('config')

    def show_store_page(self):
        self.show_page('store')

    def show_updates_page(self):
        self.show_page('updates')

    def create_control_page(self):
        page = ctk.CTkFrame(self.content_frame)
        self.pages['control'] = page

        # Кнопки управления
        control_frame = ctk.CTkFrame(page)
        control_frame.pack(fill=tk.X, padx=10, pady=5)

        start_btn = ctk.CTkButton(
            control_frame, 
            text="Запустить бота",
            command=self.start_bot
        )
        start_btn.pack(side=tk.LEFT, padx=5)

        stop_btn = ctk.CTkButton(
            control_frame,
            text="Остановить бота",
            command=self.stop_bot
        )
        stop_btn.pack(side=tk.LEFT, padx=5)

        # Лог
        log_frame = ctk.CTkFrame(page)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        log_label = ctk.CTkLabel(log_frame, text="Лог бота:")
        log_label.pack(anchor=tk.W, padx=5, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=20)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def create_modules_page(self):
        page = ctk.CTkFrame(self.content_frame)
        self.pages['modules'] = page

        # Заголовок и описание
        header_frame = ctk.CTkFrame(page)
        header_frame.pack(fill=tk.X, padx=10, pady=5)

        title = ctk.CTkLabel(
            header_frame, 
            text="Управление модулями", 
            font=("Arial", 24, "bold")
        )
        title.pack(side=tk.LEFT, pady=10, padx=10)

        # Основной контейнер с прокруткой
        main_container = ctk.CTkScrollableFrame(page)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Фреймы для модулей
        modules_frame = ctk.CTkFrame(main_container)
        modules_frame.pack(fill=tk.BOTH, expand=True)

        # Активные модули
        active_frame = ctk.CTkFrame(modules_frame)
        active_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        active_header = ctk.CTkFrame(active_frame)
        active_header.pack(fill=tk.X, padx=5, pady=5)
        
        active_label = ctk.CTkLabel(
            active_header, 
            text="Активные модули", 
            font=("Arial", 16, "bold"),
            text_color=("green")
        )
        active_label.pack(side=tk.LEFT, padx=5)
        
        self.active_count_label = ctk.CTkLabel(
            active_header, 
            text="(0)", 
            font=("Arial", 14)
        )
        self.active_count_label.pack(side=tk.LEFT)
        
        # Контейнер для списка активных модулей
        active_list_frame = ctk.CTkFrame(active_frame)
        active_list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.active_modules_list = tk.Listbox(
            active_list_frame,
            font=("Arial", 11),
            selectmode=tk.SINGLE,
            activestyle='dotbox',
            height=15,
            width=40,
            bg='#2b2b2b',
            fg='white',
            selectbackground='#1f538d',
            selectforeground='white'
        )
        self.active_modules_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Скроллбар для активных модулей
        active_scrollbar = tk.Scrollbar(active_list_frame)
        active_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.active_modules_list.config(yscrollcommand=active_scrollbar.set)
        active_scrollbar.config(command=self.active_modules_list.yview)

        # Кнопки управления
        buttons_frame = ctk.CTkFrame(modules_frame)
        buttons_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10)

        # Добавляем пространство сверху
        ctk.CTkLabel(buttons_frame, text="").pack(pady=50)

        disable_btn = ctk.CTkButton(
            buttons_frame,
            text="Отключить ➡️",
            font=("Arial", 12, "bold"),
            width=150,
            height=40,
            command=lambda: self.disable_selected_module(
                self.active_modules_list.get(self.active_modules_list.curselection()[0])
                if self.active_modules_list.curselection() else None
            )
        )
        disable_btn.pack(pady=10)

        enable_btn = ctk.CTkButton(
            buttons_frame,
            text="⬅️ Включить",
            font=("Arial", 12, "bold"),
            width=150,
            height=40,
            command=lambda: self.enable_selected_module(
                self.available_modules_list.get(self.available_modules_list.curselection()[0])
                if self.available_modules_list.curselection() else None
            )
        )
        enable_btn.pack(pady=10)

        refresh_btn = ctk.CTkButton(
            buttons_frame,
            text="🔄 Обновить",
            font=("Arial", 12, "bold"),
            width=150,
            height=40,
            command=self.update_module_lists
        )
        refresh_btn.pack(pady=10)

        # Доступные модули
        available_frame = ctk.CTkFrame(modules_frame)
        available_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        available_header = ctk.CTkFrame(available_frame)
        available_header.pack(fill=tk.X, padx=5, pady=5)
        
        available_label = ctk.CTkLabel(
            available_header, 
            text="Доступные модули", 
            font=("Arial", 16, "bold"),
            text_color=("gray70")
        )
        available_label.pack(side=tk.LEFT, padx=5)
        
        self.available_count_label = ctk.CTkLabel(
            available_header, 
            text="(0)", 
            font=("Arial", 14)
        )
        self.available_count_label.pack(side=tk.LEFT)
        
        # Контейнер для списка доступных модулей
        available_list_frame = ctk.CTkFrame(available_frame)
        available_list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.available_modules_list = tk.Listbox(
            available_list_frame,
            font=("Arial", 11),
            selectmode=tk.SINGLE,
            activestyle='dotbox',
            height=15,
            width=40,
            bg='#2b2b2b',
            fg='white',
            selectbackground='#1f538d',
            selectforeground='white'
        )
        self.available_modules_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Скроллбар для доступных модулей
        available_scrollbar = tk.Scrollbar(available_list_frame)
        available_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.available_modules_list.config(yscrollcommand=available_scrollbar.set)
        available_scrollbar.config(command=self.available_modules_list.yview)

        # Добавляем двойный клик для быстрого включения/отключения
        self.active_modules_list.bind('<Double-Button-1>', lambda e: self.disable_selected_module(
            self.active_modules_list.get(self.active_modules_list.curselection()[0])
            if self.active_modules_list.curselection() else None
        ))
        self.available_modules_list.bind('<Double-Button-1>', lambda e: self.enable_selected_module(
            self.available_modules_list.get(self.available_modules_list.curselection()[0])
            if self.available_modules_list.curselection() else None
        ))

        # Информационная панель
        info_frame = ctk.CTkFrame(main_container)
        info_frame.pack(fill=tk.X, pady=10)
        
        self.module_info_label = ctk.CTkLabel(
            info_frame, 
            text="", 
            font=("Arial", 12),
            wraplength=800
        )
        self.module_info_label.pack(pady=5)

        # Обновляем списки модулей
        self.update_module_lists()

    def create_config_page(self):
        page = ctk.CTkFrame(self.content_frame)
        self.pages['config'] = page

        # Create a scrollable frame for all content
        scrollable_frame = ctk.CTkScrollableFrame(page)
        scrollable_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Bot Token
        token_label = ctk.CTkLabel(scrollable_frame, text="Bot Token:")
        token_label.pack(anchor=tk.W, padx=10, pady=5)
        
        self.token_input = ctk.CTkEntry(scrollable_frame, width=400)
        self.token_input.pack(anchor=tk.W, padx=10, pady=5)

        # Yandex Music Token
        yandex_token_label = ctk.CTkLabel(scrollable_frame, text="Yandex Music Token:")
        yandex_token_label.pack(anchor=tk.W, padx=10, pady=5)
        
        self.yandex_token_input = ctk.CTkEntry(scrollable_frame, width=400)
        self.yandex_token_input.pack(anchor=tk.W, padx=10, pady=5)

        # Allowed Users
        allowed_users_label = ctk.CTkLabel(scrollable_frame, text="Allowed Users:")
        allowed_users_label.pack(anchor=tk.W, padx=10, pady=5)
        
        self.allowed_users_input = scrolledtext.ScrolledText(scrollable_frame, height=10, width=50)
        self.allowed_users_input.pack(anchor=tk.W, padx=10, pady=5)

        # Download Folder
        download_folder_label = ctk.CTkLabel(scrollable_frame, text="Download Folder:")
        download_folder_label.pack(anchor=tk.W, padx=10, pady=5)
        
        self.download_folder_input = ctk.CTkEntry(scrollable_frame, width=400)
        self.download_folder_input.pack(anchor=tk.W, padx=10, pady=5)

        # Max File Size
        max_file_size_label = ctk.CTkLabel(scrollable_frame, text="Max File Size (bytes):")
        max_file_size_label.pack(anchor=tk.W, padx=10, pady=5)
        
        self.max_file_size_input = ctk.CTkEntry(scrollable_frame, width=400)
        self.max_file_size_input.pack(anchor=tk.W, padx=10, pady=5)

        # Allowed Extensions
        allowed_extensions_label = ctk.CTkLabel(scrollable_frame, text="Allowed Extensions:")
        allowed_extensions_label.pack(anchor=tk.W, padx=10, pady=5)
        
        self.allowed_extensions_input = scrolledtext.ScrolledText(scrollable_frame, height=10, width=50)
        self.allowed_extensions_input.pack(anchor=tk.W, padx=10, pady=5)

        # Hidden Files
        hidden_files_section = ctk.CTkLabel(scrollable_frame, text="Hidden Files:", font=("Arial", 14, "bold"))
        hidden_files_section.pack(anchor=tk.W, padx=10, pady=(20, 5))
        
        # System Files
        system_files_label = ctk.CTkLabel(scrollable_frame, text="System Files:")
        system_files_label.pack(anchor=tk.W, padx=10, pady=5)
        
        self.system_files_input = scrolledtext.ScrolledText(scrollable_frame, height=5, width=50)
        self.system_files_input.pack(anchor=tk.W, padx=10, pady=5)

        # Temporary Files
        temp_files_label = ctk.CTkLabel(scrollable_frame, text="Temporary Files:")
        temp_files_label.pack(anchor=tk.W, padx=10, pady=5)
        
        self.temp_files_input = scrolledtext.ScrolledText(scrollable_frame, height=5, width=50)
        self.temp_files_input.pack(anchor=tk.W, padx=10, pady=5)

        # Hidden Files
        hidden_files_label = ctk.CTkLabel(scrollable_frame, text="Hidden Files:")
        hidden_files_label.pack(anchor=tk.W, padx=10, pady=5)
        
        self.hidden_files_input = scrolledtext.ScrolledText(scrollable_frame, height=5, width=50)
        self.hidden_files_input.pack(anchor=tk.W, padx=10, pady=5)

        # Backup Files
        backup_files_label = ctk.CTkLabel(scrollable_frame, text="Backup Files:")
        backup_files_label.pack(anchor=tk.W, padx=10, pady=5)
        
        self.backup_files_input = scrolledtext.ScrolledText(scrollable_frame, height=5, width=50)
        self.backup_files_input.pack(anchor=tk.W, padx=10, pady=5)

        # Save Button
        save_config_btn = ctk.CTkButton(
            scrollable_frame,
            text="Сохранить конфигурацию",
            command=self.save_config
        )
        save_config_btn.pack(anchor=tk.W, padx=10, pady=10)

    def create_store_page(self):
        page = ctk.CTkFrame(self.content_frame)
        self.pages['store'] = page

        # Заголовок
        title = ctk.CTkLabel(page, text="Магазин модулей", font=("Arial", 20))
        title.pack(pady=10)

        # Верхняя панель
        top_frame = ctk.CTkFrame(page)
        top_frame.pack(fill=tk.X, padx=10, pady=5)

        self.search_entry = ctk.CTkEntry(top_frame, placeholder_text="Поиск модулей...")
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        refresh_btn = ctk.CTkButton(
            top_frame,
            text="🔄 Обновить список",
            command=self.refresh_store
        )
        refresh_btn.pack(side=tk.LEFT, padx=5)

        # Список модулей
        self.store_modules_frame = ctk.CTkScrollableFrame(page)
        self.store_modules_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Статус загрузки
        self.store_status = ctk.CTkLabel(page, text="")
        self.store_status.pack(pady=5)

        self.refresh_store()

    def refresh_store(self):
        self.store_status.configure(text="Загрузка модулей...")
        
        # Очищаем список модулей
        for widget in self.store_modules_frame.winfo_children():
            widget.destroy()

        # Получаем доступные модули
        modules = self.module_manager.get_available_store_modules()
        search_query = self.search_entry.get().lower()

        for module in modules:
            if search_query and search_query not in module["name"].lower():
                continue
                
            # Проверяем, установлен ли модуль
            is_installed = os.path.exists(
                os.path.join(self.module_manager.modules_lib_dir, f"{module['name']}.py")
            )
            
            self.create_store_module(
                self.store_modules_frame,
                module["name"],
                module["description"],
                module["version"],
                module["dependencies"],
                module["download_url"],
                is_installed
            )

        self.store_status.configure(
            text=f"Найдено модулей: {len(modules)}"
        )

    def create_store_module(self, parent, name, description, version, dependencies, download_url, is_installed):
        module_frame = ctk.CTkFrame(parent)
        module_frame.pack(fill=tk.X, padx=5, pady=5)

        # Основная информация
        info_frame = ctk.CTkFrame(module_frame)
        info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        header_frame = ctk.CTkFrame(info_frame)
        header_frame.pack(fill=tk.X)

        name_label = ctk.CTkLabel(
            header_frame,
            text=name,
            font=("Arial", 14, "bold")
        )
        name_label.pack(side=tk.LEFT)

        version_label = ctk.CTkLabel(
            header_frame,
            text=f"v{version}",
            font=("Arial", 12)
        )
        version_label.pack(side=tk.LEFT, padx=10)

        desc_label = ctk.CTkLabel(info_frame, text=description)
        desc_label.pack(anchor=tk.W)

        if dependencies:
            dep_label = ctk.CTkLabel(
                info_frame,
                text=f"Зависимости: {', '.join(dependencies)}",
                font=("Arial", 10)
            )
            dep_label.pack(anchor=tk.W)

        # Кнопки
        button_frame = ctk.CTkFrame(module_frame)
        button_frame.pack(side=tk.RIGHT, padx=5)

        if is_installed:
            status_label = ctk.CTkLabel(
                button_frame,
                text="✓ Установлен",
                text_color="green"
            )
            status_label.pack(pady=2)
            
            update_btn = ctk.CTkButton(
                button_frame,
                text="Обновить",
                command=lambda: self.install_module(name, download_url)
            )
            update_btn.pack(pady=2)
        else:
            install_btn = ctk.CTkButton(
                button_frame,
                text="Установить",
                command=lambda: self.install_module(name, download_url)
            )
            install_btn.pack()

    def install_module(self, name, download_url):
        self.store_status.configure(text=f"Установка модуля {name}...")
        
        if self.module_manager.download_module(download_url, name):
            messagebox.showinfo(
                "Успех",
                f"Модуль {name} успешно установлен\n" +
                "Теперь вы можете активировать его во вкладке 'Модули'"
            )
            self.update_module_lists()
            self.update_config_module_list()
            self.refresh_store()
        else:
            messagebox.showerror(
                "Ошибка",
                f"Не удалось установить модуль {name}\n" +
                "Проверьте подключение к интернету и попробуйте снова"
            )
        
        self.store_status.configure(text="")

    def create_updates_page(self):
        page = ctk.CTkFrame(self.content_frame)
        self.pages['updates'] = page

        # Заголовок
        title = ctk.CTkLabel(page, text="Обновления", font=("Arial", 20))
        title.pack(pady=10)

        # Информация о версии
        self.version_frame = ctk.CTkFrame(page)
        self.version_frame.pack(fill=tk.X, padx=10, pady=5)

        self.version_label = ctk.CTkLabel(
            self.version_frame,
            text="Проверка версии...",
            font=("Arial", 12)
        )
        self.version_label.pack(side=tk.LEFT)

        check_updates_btn = ctk.CTkButton(
            self.version_frame,
            text="🔄 Проверить обновления",
            command=self.check_updates
        )
        check_updates_btn.pack(side=tk.RIGHT)

        # Список изменений
        changes_label = ctk.CTkLabel(
            page,
            text="Список изменений:",
            font=("Arial", 12, "bold")
        )
        changes_label.pack(anchor=tk.W, padx=10, pady=(10,0))

        self.updates_frame = ctk.CTkScrollableFrame(page)
        self.updates_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.check_updates()

    def check_updates(self):
        self.version_label.configure(text="Проверка обновлений...")
        
        updates = self.module_manager.check_for_updates()
        
        # Очищаем список обновлений
        for widget in self.updates_frame.winfo_children():
            widget.destroy()

        if updates:
            if updates["has_updates"]:
                # Показываем информацию о версиях
                version_info = f"Текущая версия: {updates['current_version']}\n"
                version_info += f"Доступна версия: {updates['new_version']}"
                
                self.version_label.configure(text=version_info)
                
                # Показываем изменения
                for change in updates["changes"]:
                    self.create_update_item(self.updates_frame, change)
                
                # Кнопка обновления
                update_btn = ctk.CTkButton(
                    self.updates_frame,
                    text="Установить обновление",
                    command=self.update_bot
                )
                update_btn.pack(anchor=tk.W, padx=5, pady=10)
            else:
                self.version_label.configure(
                    text=f"У вас установлена последняя версия ({updates['current_version']})"
                )
        else:
            self.version_label.configure(
                text="Ошибка проверки обновлений.\nПроверьте подключение к интернету."
            )

    def create_update_item(self, parent, change_message):
        update_frame = ctk.CTkFrame(parent)
        update_frame.pack(fill=tk.X, padx=5, pady=2)

        bullet = ctk.CTkLabel(update_frame, text="•", width=20)
        bullet.pack(side=tk.LEFT)

        message = ctk.CTkLabel(
            update_frame,
            text=change_message,
            wraplength=400,
            justify=tk.LEFT
        )
        message.pack(side=tk.LEFT, padx=5, fill=tk.X)

    def update_bot(self):
        self.version_label.configure(text="Установка обновлений...")
        
        if self.module_manager.update_bot():
            messagebox.showinfo(
                "Успех",
                "Бот успешно обновлен.\nПерезапустите приложение для применения обновлений."
            )
            self.check_updates()
        else:
            messagebox.showerror(
                "Ошибка",
                "Не удалось обновить бота.\nПроверьте подключение к интернету и попробуйте снова."
            )
        
        self.version_label.configure(text="")

    def update_module_lists(self):
        # Очищаем списки модулей
        self.active_modules_list.delete(0, tk.END)
        self.available_modules_list.delete(0, tk.END)

        # Обновляем список активных модулей
        active_modules = [m.replace('.py', '') for m in self.module_manager.get_active_modules()]
        for module in sorted(active_modules):
            self.active_modules_list.insert(tk.END, module)

        # Обновляем список доступных модулей
        available_modules = [m.replace('.py', '') for m in self.module_manager.get_available_modules()]
        for module in sorted(available_modules):
            if module not in active_modules:  # Показываем только неактивные модули
                self.available_modules_list.insert(tk.END, module)

        # Обновляем информационную панель
        total_modules = len(available_modules)
        active_count = len(active_modules)
        self.module_info_label.configure(
            text=f"Всего модулей: {total_modules} | Активных: {active_count} | Неактивных: {total_modules - active_count}"
        )
        self.active_count_label.configure(text=f"({active_count})")
        self.available_count_label.configure(text=f"({total_modules - active_count})")

    def enable_selected_module(self, module_name=None):
        """Включение выбранного модуля"""
        if module_name is None:
            selection = self.available_modules_list.curselection()
            if not selection:
                messagebox.showwarning("Предупреждение", "Выберите модуль для включения")
                return
            module_name = self.available_modules_list.get(selection[0])

        if self.module_manager.enable_module(module_name):
            # Обновляем конфигурацию
            if not hasattr(self, 'config'):
                self.config = {}
            if 'modules' not in self.config:
                self.config['modules'] = {}
            self.config['modules'][module_name.replace('.py', '')] = {'enabled': True}
            self.save_config()
            self.update_module_lists()
            messagebox.showinfo("Успех", f"Модуль {module_name} успешно включен")
        else:
            messagebox.showerror("Ошибка", f"Не удалось включить модуль {module_name}")

    def disable_selected_module(self, module_name=None):
        """Отключение выбранного модуля"""
        if module_name is None:
            selection = self.active_modules_list.curselection()
            if not selection:
                messagebox.showwarning("Предупреждение", "Выберите модуль для отключения")
                return
            module_name = self.active_modules_list.get(selection[0])

        if self.module_manager.disable_module(module_name):
            # Обновляем конфигурацию
            if module_name.replace('.py', '') in self.config.get('modules', {}):
                self.config['modules'][module_name.replace('.py', '')]['enabled'] = False
            self.save_config()
            self.update_module_lists()
            messagebox.showinfo("Успех", f"Модуль {module_name} успешно отключен")
        else:
            messagebox.showerror("Ошибка", f"Не удалось отключить модуль {module_name}")

    def load_config(self):
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                self.config = json.load(f)
                
                # Загружаем основные настройки
                self.token_input.insert(0, self.config.get('bot_token', ''))
                
                # Загружаем настройки Yandex Music
                if 'yandex_music_token' in self.config:
                    self.yandex_token_input.insert(0, self.config['yandex_music_token'])
                
                # Загружаем список разрешенных пользователей
                if 'allowed_users' in self.config:
                    self.allowed_users_input.delete('1.0', tk.END)
                    self.allowed_users_input.insert('1.0', '\n'.join(self.config['allowed_users']))
                
                # Загружаем настройки файлов
                if 'download_folder' in self.config:
                    self.download_folder_input.delete(0, tk.END)
                    self.download_folder_input.insert(0, self.config['download_folder'])
                
                if 'max_file_size' in self.config:
                    self.max_file_size_input.delete(0, tk.END)
                    self.max_file_size_input.insert(0, str(self.config['max_file_size']))
                
                if 'allowed_extensions' in self.config:
                    self.allowed_extensions_input.delete('1.0', tk.END)
                    self.allowed_extensions_input.insert('1.0', '\n'.join(self.config['allowed_extensions']))
                
                # Загружаем скрытые файлы
                if 'hidden_files' in self.config:
                    hidden = self.config['hidden_files']
                    self.system_files_input.delete('1.0', tk.END)
                    self.system_files_input.insert('1.0', '\n'.join(hidden.get('system', [])))
                    
                    self.temp_files_input.delete('1.0', tk.END)
                    self.temp_files_input.insert('1.0', '\n'.join(hidden.get('temporary', [])))
                    
                    self.hidden_files_input.delete('1.0', tk.END)
                    self.hidden_files_input.insert('1.0', '\n'.join(hidden.get('hidden', [])))
                    
                    self.backup_files_input.delete('1.0', tk.END)
                    self.backup_files_input.insert('1.0', '\n'.join(hidden.get('backup', [])))
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить конфигурацию: {str(e)}")

    def save_config(self):
        try:
            # Собираем все настройки в словарь
            config = {
                'bot_token': self.token_input.get(),
                'yandex_music_token': self.yandex_token_input.get(),
                'allowed_users': [
                    user.strip() 
                    for user in self.allowed_users_input.get('1.0', tk.END).split('\n')
                    if user.strip()
                ],
                'download_folder': self.download_folder_input.get(),
                'max_file_size': int(self.max_file_size_input.get()),
                'allowed_extensions': [
                    ext.strip() 
                    for ext in self.allowed_extensions_input.get('1.0', tk.END).split('\n')
                    if ext.strip()
                ],
                'hidden_files': {
                    'system': [
                        f.strip() 
                        for f in self.system_files_input.get('1.0', tk.END).split('\n')
                        if f.strip()
                    ],
                    'temporary': [
                        f.strip() 
                        for f in self.temp_files_input.get('1.0', tk.END).split('\n')
                        if f.strip()
                    ],
                    'hidden': [
                        f.strip() 
                        for f in self.hidden_files_input.get('1.0', tk.END).split('\n')
                        if f.strip()
                    ],
                    'backup': [
                        f.strip() 
                        for f in self.backup_files_input.get('1.0', tk.END).split('\n')
                        if f.strip()
                    ]
                }
            }
            
            # Обновляем модули
            if 'modules' in self.config:
                config['modules'] = self.config['modules']
            
            # Сохраняем конфигурацию в файл
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            
            messagebox.showinfo("Успех", "Конфигурация сохранена")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить конфигурацию: {str(e)}")

    def start_bot(self):
        try:
            if platform.system() == "Windows":
                subprocess.Popen(
                    ["start", "cmd", "/k", "python", "main.py"],
                    shell=True
                )
            else:
                subprocess.Popen(
                    ["gnome-terminal", "--", "python3", "main.py"]
                )
            self.log_text.insert(tk.END, "Бот запущен\n")
        except Exception as e:
            self.log_text.insert(tk.END, f"Ошибка запуска бота: {str(e)}\n")

    def stop_bot(self):
        try:
            if platform.system() == "Windows":
                subprocess.run(["taskkill", "/F", "/IM", "python.exe"])
            else:
                subprocess.run(["pkill", "-f", "python.*main.py"])
            self.log_text.insert(tk.END, "Бот остановлен\n")
        except Exception as e:
            self.log_text.insert(tk.END, f"Ошибка остановки бота: {str(e)}\n")

    def update_config_module_list(self):
        self.module_listbox.delete(0, tk.END)
        for module in self.module_manager.get_available_modules():
            self.module_listbox.insert(tk.END, module.replace('.py', ''))

if __name__ == '__main__':
    app = BotManager()
    app.mainloop()
