#!/bin/bash

# MP3 AutoCut - Быстрый запуск GUI (для терминала)

# Получаем директорию, где лежит этот скрипт
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Переходим в директорию проекта
cd "$SCRIPT_DIR"

# Активируем виртуальное окружение и запускаем GUI
source .venv312/bin/activate && python mp3_autocut_gui.py 