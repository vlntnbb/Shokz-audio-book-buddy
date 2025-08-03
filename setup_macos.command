#!/bin/bash

# MP3 AutoCut - Установка для macOS
# Двойной клик для первоначальной настройки

# Получаем директорию, где лежит этот скрипт
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Переходим в директорию проекта
cd "$SCRIPT_DIR"

echo "=== MP3 AutoCut - Установка для macOS ==="
echo "Директория проекта: $SCRIPT_DIR"
echo ""

# Проверяем наличие Python
echo "🔍 Проверка Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ ОШИБКА: Python 3 не найден!"
    echo "Пожалуйста, установите Python с https://www.python.org/downloads/"
    echo ""
    echo "Нажмите любую клавишу для выхода..."
    read -n 1
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo "✅ Найден: $PYTHON_VERSION"

# Проверяем наличие ffmpeg
echo ""
echo "🔍 Проверка ffmpeg..."
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  ffmpeg не найден!"
    echo "Для установки выполните: brew install ffmpeg"
    echo "Или установите Homebrew, если его нет: https://brew.sh"
    echo ""
    echo "Продолжить без ffmpeg? (программа не будет работать) [y/N]"
    read -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✅ ffmpeg найден"
fi

# Создаём виртуальное окружение
echo ""
echo "🔨 Создание виртуального окружения..."
if [ -d ".venv312" ]; then
    echo "⚠️  Виртуальное окружение уже существует"
    echo "Пересоздать? (это удалит существующее) [y/N]"
    read -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🗑️  Удаление старого окружения..."
        rm -rf .venv312
    else
        echo "Использую существующее окружение"
    fi
fi

if [ ! -d ".venv312" ]; then
    echo "📦 Создание нового виртуального окружения..."
    python3 -m venv .venv312
    if [ $? -ne 0 ]; then
        echo "❌ ОШИБКА при создании виртуального окружения!"
        echo ""
        echo "Нажмите любую клавишу для выхода..."
        read -n 1
        exit 1
    fi
    echo "✅ Виртуальное окружение создано"
fi

# Активируем окружение и устанавливаем зависимости
echo ""
echo "📚 Установка зависимостей..."
source .venv312/bin/activate

if [ ! -f "requirements.txt" ]; then
    echo "❌ ОШИБКА: Файл requirements.txt не найден!"
    echo ""
    echo "Нажмите любую клавишу для выхода..."
    read -n 1
    exit 1
fi

pip install --upgrade pip
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ ОШИБКА при установке зависимостей!"
    echo ""
    echo "Нажмите любую клавишу для выхода..."
    read -n 1
    exit 1
fi

echo ""
echo "🎉 Установка завершена успешно!"
echo ""
echo "Теперь вы можете:"
echo "  • Запускать GUI двойным кликом на start_gui.command"
echo "  • Или из терминала: ./start_gui.sh"
echo ""
echo "Нажмите любую клавишу для закрытия..."
read -n 1 