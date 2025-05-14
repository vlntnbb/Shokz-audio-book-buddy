import os
import tempfile
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from split_mp3 import split_mp3
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='.', static_url_path='')

# Настройка директорий
UPLOAD_FOLDER = 'temp_uploads'
OUTPUT_FOLDER = 'ready_mp3'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

@app.route('/')
def index():
    return send_from_directory('.', 'web_interface.html')

@app.route('/process', methods=['POST'])
def process_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Файл не найден в запросе'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400
    
    if not file.filename.lower().endswith('.mp3'):
        return jsonify({'error': 'Пожалуйста, загрузите MP3 файл'}), 400
    
    # Получение параметров
    duration = int(request.form.get('duration', 180))
    window = int(request.form.get('window', 10))
    threshold = int(request.form.get('threshold', -40))
    min_silence = int(request.form.get('minSilence', 500))
    speed = float(request.form.get('speed', 1.0))
    output_dir = request.form.get('outputDir', OUTPUT_FOLDER)
    
    # Создание директории для выходных файлов, если она не существует
    os.makedirs(output_dir, exist_ok=True)
    
    # Сохранение загруженного файла во временную директорию
    filename = secure_filename(file.filename)
    temp_filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(temp_filepath)
    
    logger.info(f"Файл сохранен: {temp_filepath}")
    logger.info(f"Параметры: duration={duration}, window={window}, threshold={threshold}, min_silence={min_silence}, speed={speed}")
    
    try:
        # Обработка файла
        split_mp3(
            temp_filepath,
            output_dir,
            target_chunk_duration_s=duration,
            search_window_s=window,
            silence_thresh_db=threshold,
            min_silence_len_ms=min_silence,
            speed_factor=speed
        )
        
        # Получение списка созданных файлов
        base_filename = os.path.splitext(filename)[0]
        output_files = [f for f in os.listdir(output_dir) if f.startswith(base_filename + '_')]
        
        # Удаление временного файла
        os.remove(temp_filepath)
        
        return jsonify({
            'success': True,
            'message': f'Файл успешно обработан. Создано {len(output_files)} частей.',
            'output_files': output_files,
            'output_dir': output_dir
        })
    
    except Exception as e:
        logger.error(f"Ошибка при обработке файла: {str(e)}")
        # Удаление временного файла в случае ошибки
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)
        
        return jsonify({
            'success': False,
            'error': f'Ошибка при обработке файла: {str(e)}'
        }), 500

@app.route('/download/<path:filename>')
def download_file(filename):
    """Обработка скачивания обработанных файлов"""
    return send_from_directory(OUTPUT_FOLDER, filename, as_attachment=True)

if __name__ == '__main__':
    print("Запуск веб-сервера на http://127.0.0.1:5000")
    app.run(debug=True, host='127.0.0.1', port=5000)