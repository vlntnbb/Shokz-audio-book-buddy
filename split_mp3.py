import os
import argparse
import sys
import shutil
import hashlib # <-- Добавляем hashlib для хеш-сумм
from pydub import AudioSegment
from pydub.silence import detect_silence
from pydub.exceptions import CouldntDecodeError # Import specific exception
from pydub.effects import normalize # <--- Импортируем normalize
import pyttsx3
from tempfile import NamedTemporaryFile
import platform
import subprocess
import builtins

# Добавим функцию для нормализации
def normalize_audio(audio_segment, target_dbfs=-1.0):
    """Нормализует громкость аудиосегмента до target_dbfs по пиковому уровню."""
    if audio_segment.dBFS == float('-inf'): # Если тишина, то не нормализуем
        print(f"    Нормализация (пиковая): Сегмент представляет собой тишину (уровень: {audio_segment.dBFS:.2f} dBFS). Нормализация не применяется.")
        return audio_segment
    
    # pydub.effects.normalize устанавливает самый громкий пик на (0 - headroom) dBFS.
    # Если target_dbfs = -0.1, то headroom = 0.1
    # Если target_dbfs = 0.0, то headroom = 0.0
    # headroom не может быть отрицательным.
    headroom = abs(target_dbfs) 
    if target_dbfs > 0: # Убедимся, что target_dbfs не положительный, т.к. это пиковый уровень
        print(f"    Предупреждение: Целевой пиковый уровень {target_dbfs} dBFS > 0. Установлен на 0 dBFS (headroom 0.0).")
        headroom = 0.0

    print(f"    Нормализация (пиковая): Начальный RMS: {audio_segment.dBFS:.2f} dBFS, Начальный пик: {audio_segment.max_dBFS:.2f} dBFS. Целевой пик: {target_dbfs:.2f} dBFS (headroom: {headroom:.2f} dB)")
    normalized_segment = normalize(audio_segment, headroom=headroom)
    print(f"    Нормализация (пиковая): RMS после: {normalized_segment.dBFS:.2f} dBFS, Пик после: {normalized_segment.max_dBFS:.2f} dBFS")
    return normalized_segment

def print(*args, **kwargs):
    kwargs['flush'] = True
    return builtins.print(*args, **kwargs)

def find_silent_split_point(audio_segment, target_time_ms, search_window_ms, silence_thresh_db, min_silence_len_ms):
    """
    Ищет точку разделения в тишине в заданном окне вокруг целевого времени.
    Возвращает время (в мс) для разделения или None, если тишина не найдена.
    """
    start_search = max(0, target_time_ms - search_window_ms // 2)
    end_search = min(len(audio_segment), target_time_ms + search_window_ms // 2)

    # Add check for valid search window relative to segment length
    if start_search >= end_search or start_search >= len(audio_segment):
         print(f"    Debug: Invalid search window [{start_search}, {end_search}] for segment length {len(audio_segment)} around {target_time_ms}ms")
         return None # Окно поиска некорректно или за пределами аудио

    search_area = audio_segment[start_search:end_search]

    # Add a check for empty search area which can cause errors
    if len(search_area) == 0:
        print(f"    Debug: Empty search area created for window [{start_search}, {end_search}]")
        return None

    try:
        # Use a slightly larger seek_step if performance is an issue, but 1 is most accurate
        silences = detect_silence(
            search_area,
            min_silence_len=min_silence_len_ms,
            silence_thresh=silence_thresh_db,
            seek_step=1 # Check every ms for finer granularity
        )
    except Exception as e:
         print(f"    Error detecting silence in window [{start_search}, {end_search}]: {e}")
         return None # Error during silence detection


    if not silences:
        # print(f"    Debug: No silence found in window [{start_search}, {end_search}] with threshold {silence_thresh_db}dB and min_len {min_silence_len_ms}ms")
        return None # Тишина не найдена в окне

    # Конвертируем время тишины относительно search_area в абсолютное время
    absolute_silences = [(s + start_search, e + start_search) for s, e in silences]

    # Ищем тишину, середина которой ближе всего к target_time_ms
    best_silence = min(
        absolute_silences,
        key=lambda s: abs(((s[0] + s[1]) / 2) - target_time_ms)
    )

    # Возвращаем середину найденного интервала тишины
    split_time = (best_silence[0] + best_silence[1]) // 2
    # print(f"    Debug: Found silences {absolute_silences}, best silence {best_silence}, split at {split_time}ms")
    return split_time


def split_mp3(input_file, output_dir, target_chunk_duration_s=100, search_window_s=10, silence_thresh_db=-40, min_silence_len_ms=500, speed_factor=1.0, target_normalization_dbfs=-0.1, enable_normalization=False):
    """
    Разделяет ОДИН MP3 файл на части по ~target_chunk_duration_s, стараясь резать по тишине.
    Сохраняет части в указанную output_dir, опционально изменяя скорость и нормализуя громкость.
    Возвращает словарь со статистикой обработки или None при ошибке.
    """
    if not os.path.exists(input_file):
        print(f"Ошибка: Файл не найден - {input_file}")
        return None

    # Validate speed factor
    if not (0.5 <= speed_factor <= 10.0): # Allow up to 10x, but atempo works best 0.5-2.0, chaining needed > 2.0
         print(f"Предупреждение: Коэффициент скорости {speed_factor} находится вне рекомендуемого диапазона (0.5-2.0) для фильтра atempo. Результат может быть неидеальным или ffmpeg может выдать ошибку для очень больших значений.")
         # For speeds > 2.0, ffmpeg needs chained atempo filters. Pydub might not handle this directly via parameters.
         # Example for 3x speed: -filter:a atempo=2.0,atempo=1.5
         # We'll try passing it directly, ffmpeg might handle simple cases > 2.0 or fail.
         if speed_factor <= 0:
             print(f"Ошибка: Коэффициент скорости должен быть положительным.")
             return None


    print(f"🎵 --- Обработка файла: {input_file} (Скорость: {speed_factor}x) ---")
    print(f"  Загрузка...")
    try:
        audio = AudioSegment.from_mp3(input_file)
    except CouldntDecodeError: # More specific error catch
         print(f"  Ошибка: Не удалось декодировать файл: {input_file}. Возможно, он поврежден или не является MP3.")
         return None
    except FileNotFoundError: # Handle case where file disappears between check and load
        print(f"  Ошибка: Файл не найден при попытке загрузки: {input_file}")
        return None
    except Exception as e:
        print(f"  Ошибка загрузки MP3 файла ({input_file}): {e}")
        print("  Убедись, что ffmpeg или libav установлены и доступны в PATH.")
        return None

    print(f"  Файл загружен (длительность: {len(audio)/1000:.2f}s).")
    total_duration_ms = len(audio)
    target_chunk_duration_ms = target_chunk_duration_s * 1000
    search_window_ms = search_window_s * 1000
    
    # Инициализация статистики
    import time
    start_time = time.time()
    original_rms = audio.dBFS
    original_peak = audio.max_dBFS
    
    stats = {
        'original_duration_ms': total_duration_ms,
        'target_duration_ms': total_duration_ms / speed_factor,  # После ускорения
        'original_rms': original_rms,
        'original_peak': original_peak,
        'chunks_count': 0,
        'total_output_size_bytes': 0,
        'rms_values': [],
        'peak_values': [],
        'speed_factor': speed_factor,
        'enable_normalization': enable_normalization,
        'processing_time_sec': 0
    }

    if not os.path.exists(output_dir):
        # print(f"  Создание выходной директории для кусков: {output_dir}")
        try:
             os.makedirs(output_dir)
        except OSError as e:
             print(f"  Ошибка создания директории {output_dir}: {e}")
             return None


    base_filename = os.path.splitext(os.path.basename(input_file))[0]
    current_pos_ms = 0
    chunk_index = 1
    # Safety counter to prevent infinite loops in edge cases
    # Estimate iterations based on original duration, speed doesn't affect number of split points
    max_iterations = (total_duration_ms // (target_chunk_duration_ms / 2)) + 20 # Increased buffer
    iterations = 0


    while current_pos_ms < total_duration_ms and iterations < max_iterations:
        iterations += 1
        ideal_split_point_ms = current_pos_ms + target_chunk_duration_ms

        if ideal_split_point_ms >= total_duration_ms - (search_window_ms / 2):
            split_point_ms = total_duration_ms
            # print(f"  Достигнут конец файла, последний кусок {chunk_index}.")
        else:
            found_split_point = find_silent_split_point(
                audio,
                ideal_split_point_ms,
                search_window_ms,
                silence_thresh_db,
                min_silence_len_ms
            )

            if found_split_point:
                if found_split_point > current_pos_ms:
                    split_point_ms = found_split_point
                    # print(f"  Найдена тишина для куска {chunk_index} около {ideal_split_point_ms/1000:.2f}s, резка в {split_point_ms/1000:.2f}s")
                else:
                    split_point_ms = ideal_split_point_ms
                    # print(f"  Предупреждение: Найденная точка тишины ({found_split_point/1000:.2f}s) <= текущей позиции ({current_pos_ms/1000:.2f}s). Используем идеальную точку {split_point_ms/1000:.2f}s.")

            else:
                split_point_ms = ideal_split_point_ms
                # print(f"  Предупреждение: Тишина не найдена для куска {chunk_index} около {ideal_split_point_ms/1000:.2f}s. Режем точно.")

            min_last_chunk_len = min_silence_len_ms # Allow last chunk to be at least min silence long
            if total_duration_ms - split_point_ms < min_last_chunk_len and split_point_ms != total_duration_ms :
                 # print(f"  Точка разделения {split_point_ms/1000:.2f}s слишком близко к концу ({total_duration_ms/1000:.2f}s). Берем все до конца.")
                 split_point_ms = total_duration_ms


        if split_point_ms <= current_pos_ms and split_point_ms != total_duration_ms:
             print(f"  Ошибка: Точка разделения {split_point_ms}ms не продвигает позицию {current_pos_ms}ms. Увеличиваем на 1мс для избежания цикла.")
             split_point_ms = current_pos_ms + 1
             if split_point_ms >= total_duration_ms:
                 split_point_ms = total_duration_ms


        if current_pos_ms >= split_point_ms:
             if current_pos_ms == total_duration_ms:
                 # print(f"  Достигнут конец файла при извлечении куска {chunk_index}. Завершение.")
                 break
             else:
                 print(f"  Ошибка: Невозможно извлечь кусок с началом {current_pos_ms}ms >= концом {split_point_ms}ms. Пропускаем итерацию.")
                 current_pos_ms = split_point_ms + 1 # Advance past the problematic point
                 if current_pos_ms >= total_duration_ms:
                     break
                 continue


        # print(f"  Извлечение куска {chunk_index}: [{current_pos_ms/1000:.2f}s - {split_point_ms/1000:.2f}s] (Длительность оригинала: {(split_point_ms - current_pos_ms)/1000:.2f}s)")
        try:
            chunk = audio[current_pos_ms:split_point_ms]
        except IndexError:
             print(f"  Ошибка (IndexError) при извлечении куска {chunk_index} ({current_pos_ms}:{split_point_ms}). Возможно, проблема с расчетом времени. Пропуск.")
             current_pos_ms = split_point_ms + 1
             if current_pos_ms >= total_duration_ms: break
             continue
        except Exception as e:
             print(f"  Ошибка при извлечении куска {chunk_index} ({current_pos_ms}:{split_point_ms}): {e}")
             current_pos_ms = split_point_ms + 1
             if current_pos_ms >= total_duration_ms: break
             continue


        output_filename = os.path.join(output_dir, f"{base_filename}_{chunk_index:03d}.mp3")

        if len(chunk) > 0:
            # Нормализация перед экспортом, если включена
            current_chunk_to_export = chunk # По умолчанию экспортируем оригинальный чанк
            if enable_normalization:
                initial_dbfs = chunk.dBFS
                print(f"  Кусок {chunk_index}: Начальный уровень громкости: {initial_dbfs:.2f} dBFS.") # Это RMS
                
                normalized_chunk = normalize_audio(chunk, target_dbfs=target_normalization_dbfs)
                # final_dbfs = normalized_chunk.dBFS # Это RMS после нормализации
                # Обновим лог, чтобы было понятнее, что это пиковая нормализация
                print(f"  Кусок {chunk_index}: Пиковая нормализация до {target_normalization_dbfs} dBFS выполнена. RMS после: {normalized_chunk.dBFS:.2f} dBFS, Пик после: {normalized_chunk.max_dBFS:.2f} dBFS.")
                current_chunk_to_export = normalized_chunk # Экспортируем нормализованный чанк
            else:
                print(f"  Кусок {chunk_index}: Нормализация отключена. RMS: {chunk.dBFS:.2f} dBFS, Пик: {chunk.max_dBFS:.2f} dBFS.")

            export_params = {}
            if speed_factor != 1.0:
                # Basic atempo filter. For speed > 2.0, might need 'atempo=2.0,atempo=...'
                # We pass it directly, ffmpeg might handle simple cases or fail gracefully.
                export_params["parameters"] = ["-filter:a", f"atempo={speed_factor}"]
                # Estimate new duration for logging
                estimated_new_duration = len(chunk) / speed_factor
                print(f"  Экспорт куска {chunk_index}: {output_filename} (Ориг. длина: {len(chunk)/1000:.2f}s, Ожид. новая: {estimated_new_duration/1000:.2f}s)")
            else:
                print(f"  Экспорт куска {chunk_index}: {output_filename} (Длительность: {len(chunk)/1000:.2f}s)")

            try:
                # Use parameters for ffmpeg filters/options
                # Экспортируем нужный чанк (оригинальный или нормализованный)
                current_chunk_to_export.export(output_filename, format="mp3", parameters=export_params.get("parameters"))
                
                # Собираем статистику
                stats['chunks_count'] += 1
                try:
                    file_size = os.path.getsize(output_filename)
                    stats['total_output_size_bytes'] += file_size
                except:
                    pass
                
                # Собираем данные о громкости финального куска
                final_rms = current_chunk_to_export.dBFS
                final_peak = current_chunk_to_export.max_dBFS
                stats['rms_values'].append(final_rms)
                stats['peak_values'].append(final_peak)
                
            except Exception as e:
                print(f"  Ошибка экспорта куска {chunk_index} ({output_filename}): {e}")
        else:
             # print(f"  Предупреждение: Кусок {chunk_index} пуст (длительность 0ms). Экспорт пропущен.")
             pass


        current_pos_ms = split_point_ms
        chunk_index += 1


    if iterations >= max_iterations:
        print(f"  Предупреждение: Достигнут лимит итераций ({max_iterations}) для файла {input_file}. Возможно, зацикливание или ошибка в логике.")

    # Завершаем сбор статистики
    stats['processing_time_sec'] = time.time() - start_time
    
    # Вычисляем средние значения громкости
    if stats['rms_values']:
        stats['avg_final_rms'] = sum(stats['rms_values']) / len(stats['rms_values'])
        stats['avg_final_peak'] = sum(stats['peak_values']) / len(stats['peak_values'])
    else:
        stats['avg_final_rms'] = 0
        stats['avg_final_peak'] = 0

    print(f"--- Обработка файла {input_file} завершена ---")
    print("═══════════════════════════════════════════════════════════")
    
    return stats


def calculate_sha256(filepath):
    """Вычисляет SHA256 хеш файла."""
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            # Читаем файл кусками, чтобы не загружать большие файлы в память целиком
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except FileNotFoundError:
        print(f"  Ошибка: Файл не найден при вычислении хеша: {filepath}")
        return None
    except Exception as e:
        print(f"  Ошибка чтения файла при вычислении хеша ({filepath}): {e}")
        return None


def copy_with_verify(source_root, dest_root):
    """Копирует файлы из source_root в dest_root с проверкой хеша."""
    abs_source_root = os.path.abspath(source_root)
    abs_dest_root = os.path.abspath(dest_root)

    print(f"\nЗапуск копирования из '{abs_source_root}' в '{abs_dest_root}' с проверкой...")

    if not os.path.isdir(abs_source_root):
        print(f"Ошибка: Исходная директория для копирования не найдена: {abs_source_root}")
        return False # Indicate failure
    elif not os.path.isdir(abs_dest_root):
        print(f"Ошибка: Путь назначения для копирования не существует или не является директорией: {abs_dest_root}")
        print("Убедитесь, что диск подключен и путь указан верно (напр., /Volumes/SWIM PRO)")
        return False # Indicate failure

    files_to_copy = []
    for root, dirs, files in os.walk(abs_source_root):
        files.sort()
        dirs.sort()
        for filename in files:
            source_path = os.path.join(root, filename)
            relative_path = os.path.relpath(source_path, abs_source_root)
            files_to_copy.append(relative_path)

    files_to_copy.sort()

    if not files_to_copy:
        print("В исходной директории нет файлов для копирования.")
        return True # Nothing to copy is not an error in itself

    print(f"Найдено {len(files_to_copy)} файлов для копирования.")
    copied_count = 0
    verified_count = 0
    copy_errors = 0
    verification_errors = 0

    for i, relative_path in enumerate(files_to_copy):
        source_file = os.path.join(abs_source_root, relative_path)
        dest_file = os.path.join(abs_dest_root, relative_path)
        dest_dir = os.path.dirname(dest_file)

        print(f"[{i+1}/{len(files_to_copy)}] Копирование: {relative_path}", end='')

        try:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(source_file, dest_file)
            copied_count += 1
            print(f" -> Скопирован...", end='')

            print(" Проверка...", end='')
            source_hash = calculate_sha256(source_file)
            dest_hash = calculate_sha256(dest_file)

            if source_hash and dest_hash and source_hash == dest_hash:
                print(" OK")
                verified_count += 1
            else:
                print(" ОШИБКА ВЕРИФИКАЦИИ!")
                if not source_hash:
                    print(f"    Не удалось вычислить хеш источника: {source_file}")
                if not dest_hash:
                    print(f"    Не удалось вычислить хеш назначения: {dest_file}")
                if source_hash and dest_hash:
                    print(f"    Источник хеш: {source_hash}")
                    print(f"    Назначение хеш: {dest_hash}")
                verification_errors += 1

        except Exception as e:
            print(f" ОШИБКА КОПИРОВАНИЯ! {e}")
            copy_errors += 1

    print("\n--------------------------------------")
    print("Копирование завершено.")
    print(f"Всего файлов для копирования: {len(files_to_copy)}")
    print(f"Успешно скопировано: {copied_count}")
    print(f"Успешно проверено: {verified_count}")
    success = True
    if copy_errors > 0:
        print(f"Ошибок копирования: {copy_errors}")
        success = False
    if verification_errors > 0:
        print(f"Ошибок верификации: {verification_errors}")
        success = False
    print("--------------------------------------")
    return success


def move_files_structure(source_root, move_dest_root):
    """Перемещает все файлы из source_root в move_dest_root, сохраняя структуру папок."""
    abs_source_root = os.path.abspath(source_root)
    abs_move_dest_root = os.path.abspath(move_dest_root)

    print(f"\nЗапуск перемещения файлов из '{abs_source_root}' в '{abs_move_dest_root}'...")

    if not os.path.isdir(abs_source_root):
        print(f"Ошибка: Исходная директория для перемещения не найдена: {abs_source_root}")
        return False

    # Создаем корневую папку назначения для перемещения, если ее нет
    try:
        os.makedirs(abs_move_dest_root, exist_ok=True)
    except OSError as e:
        print(f"Ошибка создания корневой директории для перемещения {abs_move_dest_root}: {e}")
        return False

    files_to_move = []
    # Собираем список файлов для перемещения
    for root, dirs, files in os.walk(abs_source_root):
        for filename in files:
            source_path = os.path.join(root, filename)
            relative_path = os.path.relpath(source_path, abs_source_root)
            files_to_move.append(relative_path)

    # Сортируем для предсказуемости (хотя порядок для move менее критичен)
    files_to_move.sort()

    if not files_to_move:
        print("В исходной директории нет файлов для перемещения.")
        return True

    print(f"Найдено {len(files_to_move)} файлов для перемещения.")
    moved_count = 0
    move_errors = 0

    # Перемещаем файлы
    for i, relative_path in enumerate(files_to_move):
        source_file = os.path.join(abs_source_root, relative_path)
        dest_file = os.path.join(abs_move_dest_root, relative_path)
        dest_dir = os.path.dirname(dest_file)

        # Проверяем, существует ли еще исходный файл (на случай ошибок на пред. шагах)
        if not os.path.exists(source_file):
            print(f"[{i+1}/{len(files_to_move)}] Пропуск: Исходный файл уже не существует: {relative_path}")
            continue

        print(f"[{i+1}/{len(files_to_move)}] Перемещение: {relative_path}", end='')
        try:
            # Создаем папку назначения, если нужно
            os.makedirs(dest_dir, exist_ok=True)
            # Перемещаем файл
            shutil.move(source_file, dest_file)
            moved_count += 1
            print(" -> OK")
        except Exception as e:
            print(f" ОШИБКА ПЕРЕМЕЩЕНИЯ! {e}")
            move_errors += 1

    # После перемещения всех файлов, удаляем пустые директории в источнике
    print(f"\nПроверка и удаление пустых папок в исходной директории: {abs_source_root}...")
    deleted_folders_count = 0
    try:
        # Проходим по дереву папок снизу вверх (topdown=False)
        # Это важно, чтобы сначала пытаться удалить дочерние папки, а потом родительские
        for root, dirs, files in os.walk(abs_source_root, topdown=False):
            if not dirs and not files: # Если в папке нет ни подпапок, ни файлов
                # Проверяем, что это не сама корневая папка, из которой перемещали,
                # если только она не была единственной и теперь пуста.
                # Хотя os.rmdir(abs_source_root) сработает, если она пуста.
                try:
                    os.rmdir(root)
                    print(f"  Удалена пустая папка: {root}")
                    deleted_folders_count +=1
                except OSError as e:
                    # Возможна ошибка, если папка не пуста (например, из-за .DS_Store или других скрытых файлов)
                    # или если это корень файловой системы (хотя это маловероятно здесь)
                    print(f"  Не удалось удалить папку {root}: {e}")
        if deleted_folders_count > 0:
            print(f"Удалено пустых папок: {deleted_folders_count}")
        else:
            print("Пустых папок для удаления не найдено.")
    except Exception as e: # Более общее исключение на случай непредвиденных ошибок с os.walk
        print(f"Ошибка при попытке удаления пустых исходных папок: {e}")


    print("\n--------------------------------------")
    print("Перемещение завершено.")
    print(f"Всего файлов для перемещения: {len(files_to_move)}")
    print(f"Успешно перемещено: {moved_count}")
    success = True
    if move_errors > 0:
        print(f"Ошибок перемещения: {move_errors}")
        success = False
    print("--------------------------------------")
    return success


def get_total_and_cumulative_durations(mp3_files):
    total = 0
    cumulative = [0]
    total_files = len(mp3_files)
    
    if total_files == 0:
        return total, cumulative[:-1]
    
    print(f"Анализ длительностей {total_files} MP3 файлов...")
    
    for i, f in enumerate(mp3_files):
        print(f"  [{i+1}/{total_files}] Анализ: {os.path.basename(f)}")
        try:
            dur = len(AudioSegment.from_mp3(f))
            total += dur
            cumulative.append(total)
        except Exception as e:
            print(f"    Ошибка при анализе файла {f}: {e}")
            cumulative.append(total)  # добавляем текущий total без изменений
    
    hours, minutes = format_time(total)
    print(f"Анализ завершен. Общая длительность: {hours}ч {minutes}м")
    
    return total, cumulative[:-1]  # cumulative[i] — сумма до i-го файла

def tts_to_wav(text, lang='ru'):
    with NamedTemporaryFile(delete=False, suffix='.wav') as f:
        if platform.system() == 'Darwin':
            # Используем системный say с голосом Yuri (Enhanced)
            voice = 'Yuri (Enhanced)'
            subprocess.run(['say', '-v', voice, '-o', f.name, '--data-format=LEI16@44100', text])
        else:
            # pyttsx3 для Windows/Linux
            engine = pyttsx3.init()
            engine.setProperty('rate', 180)
            # Пытаемся найти русский голос, если нет — используем дефолт
            voices = engine.getProperty('voices')
            ru_voices = [v.id for v in voices if 'ru' in v.id or 'russian' in v.name.lower()]
            if ru_voices:
                engine.setProperty('voice', ru_voices[0])
            engine.save_to_file(text, f.name)
            engine.runAndWait()
        return f.name

def format_time(ms):
    s = ms // 1000
    h = s // 3600
    m = (s % 3600) // 60
    return h, m

def format_size(bytes_size):
    """Форматирует размер в байтах в человекочитаемый формат."""
    for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} ТБ"

def print_processing_statistics(all_stats, total_original_duration, total_target_duration, 
                                total_chunks, total_output_size, total_processing_time, 
                                processed_files, speed_factor, normalization_enabled):
    """Выводит подробную статистику обработки."""
    print("\n" + "="*70)
    print("📊 ПОДРОБНАЯ СТАТИСТИКА ОБРАБОТКИ")
    print("="*70)
    
    # Временные характеристики
    orig_h, orig_m = format_time(total_original_duration)
    target_h, target_m = format_time(total_target_duration)
    
    print(f"🕒 Временные характеристики:")
    print(f"   Исходная длительность:  {orig_h}ч {orig_m}м ({total_original_duration/1000:.1f}с)")
    print(f"   Итоговая длительность:   {target_h}ч {target_m}м ({total_target_duration/1000:.1f}с)")
    if speed_factor != 1.0:
        time_saved = total_original_duration - total_target_duration
        time_saved_h, time_saved_m = format_time(time_saved)
        print(f"   Экономия времени:        {time_saved_h}ч {time_saved_m}м ({speed_factor:.2f}x ускорение)")
    
    # Файловые характеристики
    print(f"\n📁 Файловые характеристики:")
    print(f"   Обработано файлов:       {processed_files}")
    print(f"   Создано кусков:          {total_chunks}")
    print(f"   Общий размер результата: {format_size(total_output_size)}")
    if processed_files > 0:
        print(f"   Среднее кусков на файл:  {total_chunks / processed_files:.1f}")
        print(f"   Средний размер куска:    {format_size(total_output_size / total_chunks) if total_chunks > 0 else '0 Б'}")
    
    # Аудио характеристики
    if all_stats:
        original_rms_values = []
        original_peak_values = []
        final_rms_values = []
        final_peak_values = []
        
        for stat in all_stats:
            if stat['original_rms'] and stat['original_rms'] != float('-inf'):
                original_rms_values.append(stat['original_rms'])
            if stat['original_peak'] and stat['original_peak'] != float('-inf'):
                original_peak_values.append(stat['original_peak'])
            if stat['rms_values']:
                final_rms_values.extend([rms for rms in stat['rms_values'] if rms != float('-inf')])
            if stat['peak_values']:
                final_peak_values.extend([peak for peak in stat['peak_values'] if peak != float('-inf')])
        
        print(f"\n🔊 Аудио характеристики:")
        if original_rms_values:
            avg_orig_rms = sum(original_rms_values) / len(original_rms_values)
            print(f"   Исходный средний RMS:    {avg_orig_rms:.1f} dBFS")
        if original_peak_values:
            avg_orig_peak = sum(original_peak_values) / len(original_peak_values)
            print(f"   Исходный средний пик:    {avg_orig_peak:.1f} dBFS")
        
        if final_rms_values:
            avg_final_rms = sum(final_rms_values) / len(final_rms_values)
            print(f"   Итоговый средний RMS:    {avg_final_rms:.1f} dBFS")
        if final_peak_values:
            avg_final_peak = sum(final_peak_values) / len(final_peak_values)
            print(f"   Итоговый средний пик:    {avg_final_peak:.1f} dBFS")
        
        if normalization_enabled and original_rms_values and final_rms_values:
            rms_change = avg_final_rms - avg_orig_rms
            print(f"   Изменение RMS:           {rms_change:+.1f} dBFS")
    
    # Производительность
    print(f"\n⚡ Производительность:")
    print(f"   Время обработки:         {total_processing_time:.1f} сек")
    if processed_files > 0:
        print(f"   Время на файл:           {total_processing_time / processed_files:.1f} сек/файл")
    if total_original_duration > 0:
        speed_ratio = (total_original_duration / 1000) / total_processing_time
        print(f"   Скорость обработки:      {speed_ratio:.1f}x от реального времени")
    
    print("="*70)

def plural_ru(n, form1, form2, form5):
    """Склоняет русское существительное по числу: 1, 2-4, 5+ (например, процент/процента/процентов)."""
    n = abs(n) % 100
    n1 = n % 10
    if 10 < n < 20:
        return form5
    if n1 == 1:
        return form1
    if 2 <= n1 <= 4:
        return form2
    return form5

if __name__ == "__main__":
    import sys
    if '--test-plural' in sys.argv:
        print('Тесты для plural_ru:')
        test_cases = [
            (1, 'процент', 'процента', 'процентов', 'процент'),
            (2, 'процент', 'процента', 'процентов', 'процента'),
            (5, 'процент', 'процента', 'процентов', 'процентов'),
            (11, 'процент', 'процента', 'процентов', 'процентов'),
            (21, 'процент', 'процента', 'процентов', 'процент'),
            (22, 'процент', 'процента', 'процентов', 'процента'),
            (25, 'процент', 'процента', 'процентов', 'процентов'),
            (101, 'процент', 'процента', 'процентов', 'процент'),
            (0, 'процент', 'процента', 'процентов', 'процентов'),
            (-1, 'процент', 'процента', 'процентов', 'процент'),
            (112, 'процент', 'процента', 'процентов', 'процентов'),
            (4, 'минута', 'минуты', 'минут', 'минуты'),
            (14, 'минута', 'минуты', 'минут', 'минут'),
            (23, 'час', 'часа', 'часов', 'часа'),
            (1004, 'час', 'часа', 'часов', 'часа'),
        ]
        errors = 0
        for n, f1, f2, f5, expected in test_cases:
            result = plural_ru(n, f1, f2, f5)
            ok = '✅' if result == expected else '❌'
            if result != expected:
                errors += 1
            print(f'{ok} {n} → {result} (ожидалось: {expected})')
        if errors == 0:
            print('Все тесты пройдены успешно!')
        else:
            print(f'Ошибок: {errors}')
        sys.exit(0)

    parser = argparse.ArgumentParser(
        description="Рекурсивно ищет MP3, разделяет, изменяет скорость, копирует и перемещает результат.",
        formatter_class=argparse.RawTextHelpFormatter
        )
    # Добавляем группу для режимов работы
    mode_group = parser.add_argument_group('Режимы работы')
    mode_group.add_argument("--copy-only", action='store_true', help="Только скопировать файлы из папки --output-dir в --copy-to, затем переместить их в copied_mp3.")

    # Аргументы для путей
    path_group = parser.add_argument_group('Пути')
    path_group.add_argument("-i", "--input-dir", default="source_mp3", help="Папка с исходными MP3 (для обработки). По умолчанию: source_mp3.")
    path_group.add_argument("-o", "--output-dir", default="ready_mp3", help="Папка для сохранения/чтения результатов. По умолчанию: ready_mp3.")
    path_group.add_argument("--copy-to", help="Папка назначения для копирования (напр., /Volumes/DRIVE). Обязателен для --copy-only.")

    # Аргументы для обработки
    processing_group = parser.add_argument_group('Параметры обработки (игнорируются при --copy-only)')
    processing_group.add_argument("-d", "--duration", type=int, default=100, help="Желаемая длительность куска в сек. По умолчанию: 100.")
    processing_group.add_argument("-w", "--window", type=int, default=10, help="Окно поиска тишины в сек. (+/- window/2). По умолчанию: 10.")
    processing_group.add_argument("-t", "--threshold", type=int, default=-40, help="Порог тишины в dBFS. По умолчанию: -40.")
    processing_group.add_argument("-m", "--min-silence", type=int, default=500, help="Мин. длина тишины в мс. По умолчанию: 500.")
    processing_group.add_argument("-s", "--speed", type=float, default=1.0, help="Коэффициент скорости (0.5-2.0). По умолчанию: 1.0.")
    processing_group.add_argument("--skip-existing", action='store_true', help="Пропускать обработку, если 1-й кусок уже есть.")
    processing_group.add_argument("--tts-progress", action='store_true', help="Вставлять голосовое сообщение о прогрессе в первый кусок каждого файла")
    processing_group.add_argument("--tts-progress-grid", action='store_true', help="Сообщение о прогрессе не чаще чем каждые 5%%")
    # Добавляем аргумент для уровня нормализации
    processing_group.add_argument("--norm-dbfs", type=float, default=-0.1, help="Целевой уровень нормализации в dBFS (если включена). По умолчанию: -0.1.")
    # Добавляем флаг для включения нормализации
    processing_group.add_argument("--enable-normalization", action='store_true', help="Включить нормализацию громкости.")

    args = parser.parse_args()

    # Папка для перемещенных файлов
    MOVE_TARGET_DIR = "copied_mp3"

    if args.copy_only:
        print("--- РЕЖИМ: Только копирование и перемещение ---")
        if not args.copy_to:
            parser.error("--copy-to требуется при использовании --copy-only.")
        
        # Выполняем копирование
        copy_success = copy_with_verify(args.output_dir, args.copy_to)
        
        # Если копирование успешно, перемещаем
        if copy_success:
            move_success = move_files_structure(args.output_dir, MOVE_TARGET_DIR)
            sys.exit(0 if move_success else 1)
        else:
            print("Копирование не удалось. Перемещение не будет выполнено.")
            sys.exit(1)

    else:
        print("--- РЕЖИМ: Обработка, копирование и перемещение (если указано --copy-to) ---")
        input_root_dir = args.input_dir
        output_root_dir = args.output_dir

        # --- Проверка ffmpeg --- 
        try:
            print("Проверка наличия ffmpeg...")
            ff_test_cmd = "ffmpeg -version > /dev/null 2>&1" if os.name != 'nt' else "ffmpeg -version > NUL 2>&1"
            exit_code = os.system(ff_test_cmd)
            if exit_code != 0:
                print("\n!!! ОШИБКА: ffmpeg не найден или не доступен в PATH.")
                print("Пожалуйста, установите ffmpeg: https://ffmpeg.org/download.html")
                print("macOS (Homebrew): brew install ffmpeg")
                print("Debian/Ubuntu: sudo apt update && sudo apt install ffmpeg")
                print("Windows: Скачайте с сайта и добавьте в PATH.")
                sys.exit(1)
            print("ffmpeg найден.")
        except Exception as e:
             print(f"\nНе удалось проверить ffmpeg: {e}")
             sys.exit(1)

        # --- Создание директорий --- 
        print(f"Директория источник: {os.path.abspath(input_root_dir)}")
        print(f"Директория назначения: {os.path.abspath(output_root_dir)}")
        if not os.path.isdir(input_root_dir):
             print(f"Создание директории источника: {input_root_dir}")
             os.makedirs(input_root_dir)
        if not os.path.isdir(output_root_dir):
             print(f"Создание директории назначения: {output_root_dir}")
             os.makedirs(output_root_dir)

        print("\nНачало сканирования и обработки...")
        found_files = 0
        processed_files = 0
        error_files = 0

        # --- Сканирование MP3 файлов ---
        print("Сканирование MP3 файлов в директории...")
        import glob
        all_mp3 = []
        for root, dirs, files in os.walk(input_root_dir):
            files.sort()
            for f in files:
                if f.lower().endswith('.mp3'):
                    all_mp3.append(os.path.join(root, f))
        all_mp3.sort()  # сортировка по имени
        print(f"Найдено {len(all_mp3)} MP3 файлов для обработки")
        
        # --- Вычисляем длительности для TTS progress (если включен) ---
        if args.tts_progress:
            total_dur, cumulative_durs = get_total_and_cumulative_durations(all_mp3)
        else:
            total_dur, cumulative_durs = 0, [0] * len(all_mp3)
        
        # Переменная для отслеживания последнего процента с TTS сообщением (для режима grid)
        last_tts_progress_grid = -1
        
        # Инициализация общей статистики
        import time
        total_start_time = time.time()
        all_stats = []
        total_original_duration = 0
        total_target_duration = 0
        total_chunks = 0
        total_output_size = 0

        # --- Рекурсивный обход и обработка ---
        print(f"\nНачало обработки файлов...") 
        for idx, (root, dirs, files) in enumerate(os.walk(input_root_dir)):
            files.sort()
            mp3_files = [f for f in files if f.lower().endswith('.mp3')]
            if not mp3_files:
                continue
            relative_path = os.path.relpath(root, input_root_dir)
            current_output_dir = os.path.join(output_root_dir, relative_path)
            if not os.path.isdir(current_output_dir):
                try:
                    os.makedirs(current_output_dir)
                except OSError as e:
                    print(f"Ошибка создания поддиректории {current_output_dir}: {e}. Пропуск файлов в этой папке.")
                    error_files += len(mp3_files)
                    continue
            for file_idx, filename in enumerate(mp3_files):
                found_files += 1
                input_file_path = os.path.join(root, filename)
                base_output_name = os.path.splitext(filename)[0]
                potential_first_chunk = os.path.join(current_output_dir, f"{base_output_name}_001.mp3")
                if args.skip_existing and os.path.exists(potential_first_chunk):
                    print(f"--- Пропуск файла (найден существующий кусок): {input_file_path} ---")
                    continue
                if args.tts_progress:
                    # --- вычисляем процент и генерируем TTS ---
                    try:
                        file_idx_in_all = all_mp3.index(input_file_path)
                    except ValueError:
                        file_idx_in_all = 0
                    percent = int(round(100 * cumulative_durs[file_idx_in_all] / total_dur)) if total_dur > 0 else 0
                    
                    # Проверяем, нужно ли вставлять TTS сообщение
                    should_insert_tts = True
                    if args.tts_progress_grid:
                        # Режим grid: вставляем только если прогресс >= 5% и не было сообщения в текущем 5% диапазоне
                        if percent < 5:
                            should_insert_tts = False
                        else:
                            current_grid_position = (percent // 5) * 5  # 5, 10, 15, 20, ...
                            if current_grid_position <= last_tts_progress_grid:
                                should_insert_tts = False
                            else:
                                last_tts_progress_grid = current_grid_position
                    
                    if should_insert_tts:
                        h, m = format_time(total_dur)
                        percent_word = plural_ru(percent, 'процент', 'процента', 'процентов')
                        hour_word = plural_ru(h, 'час', 'часа', 'часов')
                        minute_word = plural_ru(m, 'минута', 'минуты', 'минут')
                        tts_text = f"вы прослушали {percent} {percent_word} книги длительностью {h} {hour_word} {m} {minute_word}"
                        print(f"  📢 Генерация TTS сообщения: \"{tts_text}\"")
                        tts_wav = tts_to_wav(tts_text)
                        print(f"  ✅ TTS сообщение готово, будет добавлено в первый кусок")
                    else:
                        tts_wav = None
                        if args.tts_progress_grid:
                            print(f"  ⏭️  TTS сообщение пропущено для {percent}% (режим grid: не чаще каждых 5%)")
                        else:
                            print(f"  ⏭️  TTS сообщение пропущено для {percent}%")
                    # --- нарезка ---
                    def split_mp3_with_tts(input_file, output_dir, *args_, **kwargs_):
                        from pydub import AudioSegment
                        chunks = []
                        audio = AudioSegment.from_mp3(input_file)
                        file_stats = split_mp3(input_file, output_dir, *args_, **kwargs_)
                        first_chunk = os.path.join(output_dir, f"{base_output_name}_001.mp3")
                        if os.path.exists(first_chunk) and tts_wav:
                            print(f"  🔊 Добавление TTS сообщения в начало первого куска: {os.path.basename(first_chunk)}")
                            seg1 = AudioSegment.from_wav(tts_wav)
                            seg2 = AudioSegment.from_mp3(first_chunk)
                            combined = seg1 + seg2
                            combined.export(first_chunk, format="mp3")
                            os.remove(tts_wav)
                            print(f"  🎯 TTS сообщение успешно добавлено в файл")
                        return file_stats
                    try:
                        file_stats = split_mp3_with_tts(
                            input_file_path,
                            current_output_dir,
                            target_chunk_duration_s=args.duration,
                            search_window_s=args.window,
                            silence_thresh_db=args.threshold,
                            min_silence_len_ms=args.min_silence,
                            speed_factor=args.speed,
                            target_normalization_dbfs=args.norm_dbfs,
                            enable_normalization=args.enable_normalization
                        )
                        if file_stats:
                            all_stats.append(file_stats)
                            total_original_duration += file_stats['original_duration_ms']
                            total_target_duration += file_stats['target_duration_ms']
                            total_chunks += file_stats['chunks_count']
                            total_output_size += file_stats['total_output_size_bytes']
                        processed_files += 1
                    except Exception as e:
                        print(f"\n!!! КРИТИЧЕСКАЯ ОШИБКА при обработке файла {input_file_path}: {e}")
                        print("    Продолжение со следующим файлом...\n")
                        error_files += 1
                else:
                    try:
                        file_stats = split_mp3(
                            input_file_path,
                            current_output_dir,
                            target_chunk_duration_s=args.duration,
                            search_window_s=args.window,
                            silence_thresh_db=args.threshold,
                            min_silence_len_ms=args.min_silence,
                            speed_factor=args.speed,
                            target_normalization_dbfs=args.norm_dbfs,
                            enable_normalization=args.enable_normalization
                        )
                        if file_stats:
                            all_stats.append(file_stats)
                            total_original_duration += file_stats['original_duration_ms']
                            total_target_duration += file_stats['target_duration_ms']
                            total_chunks += file_stats['chunks_count']
                            total_output_size += file_stats['total_output_size_bytes']
                        processed_files += 1
                    except Exception as e:
                        print(f"\n!!! КРИТИЧЕСКАЯ ОШИБКА при обработке файла {input_file_path}: {e}")
                        print("    Продолжение со следующим файлом...\n")
                        error_files += 1

        # --- Вывод подробной статистики обработки --- 
        total_processing_time = time.time() - total_start_time
        
        print("\n======================================")
        print("Обработка завершена.")
        print(f"Найдено MP3 файлов: {found_files}")
        print(f"Обработано файлов: {processed_files}")
        if error_files > 0:
            print(f"Файлов с ошибками/пропущено при обработке: {error_files}")
        print(f"Результаты сохранены в: {os.path.abspath(output_root_dir)}")
        print("======================================")
        
        # Выводим подробную статистику если есть обработанные файлы
        if processed_files > 0 and all_stats:
            print_processing_statistics(
                all_stats, 
                total_original_duration, 
                total_target_duration,
                total_chunks, 
                total_output_size, 
                total_processing_time,
                processed_files, 
                args.speed, 
                args.enable_normalization
            )

        # --- Копирование и Перемещение после обработки --- 
        if args.copy_to:
            copy_success = copy_with_verify(output_root_dir, args.copy_to)
            # Если копирование успешно, перемещаем
            if copy_success:
                move_files_structure(output_root_dir, MOVE_TARGET_DIR)
                # Здесь не выходим из скрипта, просто сообщаем результат перемещения
            else:
                print("Копирование не удалось. Перемещение не будет выполнено.")
        else:
            print("\nКопирование на внешний диск не запрашивалось (опция --copy-to не указана), перемещение не выполняется.") 
            print("\nКопирование на внешний диск не запрашивалось (опция --copy-to не указана), перемещение не выполняется.") 