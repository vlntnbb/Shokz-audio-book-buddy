#!/bin/bash

# MP3 AutoCut - Быстрый запуск GUI для macOS
# Двойной клик для запуска программы

# Получаем директорию, где лежит этот скрипт
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Переходим в директорию проекта
cd "$SCRIPT_DIR"

echo "=== MP3 AutoCut - Запуск GUI ==="
echo "Директория проекта: $SCRIPT_DIR"

# Проверяем существование виртуального окружения
if [ ! -d ".venv312" ]; then
    echo "❌ ОШИБКА: Виртуальное окружение .venv312 не найдено!"
    echo "Пожалуйста, сначала создайте виртуальное окружение:"
    echo "python3 -m venv .venv312"
    echo "source .venv312/bin/activate"
    echo "pip install -r requirements.txt"
    echo ""
    echo "Нажмите любую клавишу для выхода..."
    read -n 1
    exit 1
fi

# Проверяем существование GUI файла
if [ ! -f "mp3_autocut_gui.py" ]; then
    echo "❌ ОШИБКА: Файл mp3_autocut_gui.py не найден!"
    echo "Убедитесь, что вы находитесь в правильной директории проекта."
    echo ""
    echo "Нажмите любую клавишу для выхода..."
    read -n 1
    exit 1
fi

echo "✅ Активация виртуального окружения..."
source .venv312/bin/activate

echo "✅ Запуск MP3 AutoCut GUI..."
echo "Окно программы должно открыться сейчас..."
echo ""
echo "💡 Это окно терминала можно закрыть после появления GUI"
echo ""

# Запускаем GUI
python mp3_autocut_gui.py

echo ""
echo "Программа завершена."
echo "Нажмите любую клавишу для закрытия этого окна..."
read -n 1 