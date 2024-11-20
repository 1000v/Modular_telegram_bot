# Modular_telegram_bot
Modular_telegram_bot


Надо запонить config.json перед работой
'''
{
    "bot_token": "токен от бота в тг",
    "allowed_users": [
        "Id пользователя которому нужно дать доступ"
    ],
    "yandex_music_token": "Токен от яндекс музыки",
    "download_folder": "downloads",
    "max_file_size": 50000000,
    "allowed_extensions": [
        ".txt",
        ".pdf",
        ".jpg",
        ".png"
    ],
    "hidden_files": {
        "system": [
            ".dll",
            ".sys",
            ".exe",
            ".bin"
        ],
        "temporary": [
            ".tmp",
            ".temp",
            ".cache"
        ],
        "hidden": [
            ".git",
            ".env",
            ".vscode",
            ".idea"
        ],
        "backup": [
            ".bak",
            ".backup",
            "~"
        ]
    }
}
'''
