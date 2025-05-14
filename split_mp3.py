import os
import argparse
import sys
import shutil
import hashlib # <-- Добавляем hashlib для хеш-сумм
from pydub import AudioSegment
from pydub.silence import detect_silence
from pydub.exceptions import CouldntDecodeError # Import specific exception

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


def split_mp3(input_file, output_dir, target_chunk_duration_s=180, search_window_s=10, silence_thresh_db=-40, min_silence_len_ms=500, speed_factor=1.0):
    """
    Разделяет ОДИН MP3 файл на части по ~target_chunk_duration_s, стараясь резать по тишине.
    Сохраняет части в указанную output_dir, опционально изменяя скорость.
    """
    if not os.path.exists(input_file):
        print(f"Ошибка: Файл не найден - {input_file}")
        return

    # Validate speed factor
    if not (0.5 <= speed_factor <= 10.0): # Allow up to 10x, but atempo works best 0.5-2.0, chaining needed > 2.0
         print(f"Предупреждение: Коэффициент скорости {speed_factor} находится вне рекомендуемого диапазона (0.5-2.0) для фильтра atempo. Результат может быть неидеальным или ffmpeg может выдать ошибку для очень больших значений.")
         # For speeds > 2.0, ffmpeg needs chained atempo filters. Pydub might not handle this directly via parameters.
         # Example for 3x speed: -filter:a atempo=2.0,atempo=1.5
         # We'll try passing it directly, ffmpeg might handle simple cases > 2.0 or fail.
         if speed_factor <= 0:
             print(f"Ошибка: Коэффициент скорости должен быть положительным.")
             return


    print(f"--- Обработка файла: {input_file} (Скорость: {speed_factor}x) ---")
    print(f"  Загрузка...")
    try:
        audio = AudioSegment.from_mp3(input_file)
    except CouldntDecodeError: # More specific error catch
         print(f"  Ошибка: Не удалось декодировать файл: {input_file}. Возможно, он поврежден или не является MP3.")
         return
    except FileNotFoundError: # Handle case where file disappears between check and load
        print(f"  Ошибка: Файл не найден при попытке загрузки: {input_file}")
        return
    except Exception as e:
        print(f"  Ошибка загрузки MP3 файла ({input_file}): {e}")
        print("  Убедись, что ffmpeg или libav установлены и доступны в PATH.")
        return

    print(f"  Файл загружен (длительность: {len(audio)/1000:.2f}s).")
    total_duration_ms = len(audio)
    target_chunk_duration_ms = target_chunk_duration_s * 1000
    search_window_ms = search_window_s * 1000

    if not os.path.exists(output_dir):
        # print(f"  Создание выходной директории для кусков: {output_dir}")
        try:
             os.makedirs(output_dir)
        except OSError as e:
             print(f"  Ошибка создания директории {output_dir}: {e}")
             return


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
                 chunk.export(output_filename, format="mp3", parameters=export_params.get("parameters"))
             except Exception as e:
                 print(f"  Ошибка экспорта куска {chunk_index} ({output_filename}): {e}")
        else:
             # print(f"  Предупреждение: Кусок {chunk_index} пуст (длительность 0ms). Экспорт пропущен.")
             pass


        current_pos_ms = split_point_ms
        chunk_index += 1


    if iterations >= max_iterations:
        print(f"  Предупреждение: Достигнут лимит итераций ({max_iterations}) для файла {input_file}. Возможно, зацикливание или ошибка в логике.")


    print(f"--- Обработка файла {input_file} завершена ---")


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

    # Попытка удалить пустые директории в источнике (опционально)
    # Это может быть сложно и рискованно, если в папке есть что-то еще.
    # Пока оставим исходную структуру папок пустой.
    # try:
    #     for root, dirs, files in os.walk(abs_source_root, topdown=False):
    #         if not dirs and not files:
    #             print(f"Удаление пустой исходной папки: {root}")
    #             os.rmdir(root)
    # except OSError as e:
    #     print(f"Ошибка при удалении пустых исходных папок: {e}")

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


if __name__ == "__main__":
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
    processing_group.add_argument("-d", "--duration", type=int, default=180, help="Желаемая длительность куска в сек. По умолчанию: 180.")
    processing_group.add_argument("-w", "--window", type=int, default=10, help="Окно поиска тишины в сек. (+/- window/2). По умолчанию: 10.")
    processing_group.add_argument("-t", "--threshold", type=int, default=-40, help="Порог тишины в dBFS. По умолчанию: -40.")
    processing_group.add_argument("-m", "--min-silence", type=int, default=500, help="Мин. длина тишины в мс. По умолчанию: 500.")
    processing_group.add_argument("-s", "--speed", type=float, default=1.0, help="Коэффициент скорости (0.5-2.0). По умолчанию: 1.0.")
    processing_group.add_argument("--skip-existing", action='store_true', help="Пропускать обработку, если 1-й кусок уже есть.")

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

        # --- Рекурсивный обход и обработка --- 
        for root, dirs, files in os.walk(input_root_dir):
            files.sort()
            dirs.sort()
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

            for filename in mp3_files:
                found_files += 1
                input_file_path = os.path.join(root, filename)
                base_output_name = os.path.splitext(filename)[0]
                potential_first_chunk = os.path.join(current_output_dir, f"{base_output_name}_001.mp3")

                if args.skip_existing and os.path.exists(potential_first_chunk):
                    print(f"--- Пропуск файла (найден существующий кусок): {input_file_path} ---")
                    continue

                try:
                     split_mp3(
                        input_file_path,
                        current_output_dir,
                        target_chunk_duration_s=args.duration,
                        search_window_s=args.window,
                        silence_thresh_db=args.threshold,
                        min_silence_len_ms=args.min_silence,
                        speed_factor=args.speed
                     )
                     processed_files += 1
                except Exception as e:
                     print(f"\n!!! КРИТИЧЕСКАЯ ОШИБКА при обработке файла {input_file_path}: {e}")
                     print("    Продолжение со следующим файлом...\n")
                     error_files += 1

        # --- Вывод статистики обработки --- 
        print("\n======================================")
        print("Обработка завершена.")
        print(f"Найдено MP3 файлов: {found_files}")
        print(f"Обработано файлов: {processed_files}")
        if error_files > 0:
            print(f"Файлов с ошибками/пропущено при обработке: {error_files}")
        print(f"Результаты сохранены в: {os.path.abspath(output_root_dir)}")
        print("======================================")

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