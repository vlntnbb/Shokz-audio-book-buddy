document.addEventListener('DOMContentLoaded', function() {
    // Элементы интерфейса
    const dropArea = document.getElementById('dropArea');
    const fileInput = document.getElementById('fileInput');
    const fileInfo = document.getElementById('fileInfo');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const clearFileBtn = document.getElementById('clearFileBtn');
    const processBtn = document.getElementById('processBtn');
    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');
    const logOutput = document.getElementById('logOutput');
    const changeOutputBtn = document.getElementById('changeOutputBtn');
    const outputPath = document.getElementById('outputPath');

    // Ползунки параметров
    const durationSlider = document.getElementById('durationSlider');
    const durationValue = document.getElementById('durationValue');
    const windowSlider = document.getElementById('windowSlider');
    const windowValue = document.getElementById('windowValue');
    const thresholdSlider = document.getElementById('thresholdSlider');
    const thresholdValue = document.getElementById('thresholdValue');
    const minSilenceSlider = document.getElementById('minSilenceSlider');
    const minSilenceValue = document.getElementById('minSilenceValue');
    const speedSlider = document.getElementById('speedSlider');
    const speedValue = document.getElementById('speedValue');

    // Переменная для хранения выбранного файла
    let selectedFile = null;

    // Обработчики событий для drag and drop
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, unhighlight, false);
    });

    function highlight() {
        dropArea.classList.add('drag-over');
    }

    function unhighlight() {
        dropArea.classList.remove('drag-over');
    }

    // Обработка события drop
    dropArea.addEventListener('drop', handleDrop, false);

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        
        if (files.length > 0 && files[0].type === 'audio/mpeg') {
            handleFiles(files);
        } else {
            logMessage('Ошибка: Пожалуйста, выберите MP3 файл.');
        }
    }

    // Обработка выбора файла через диалог
    fileInput.addEventListener('change', function() {
        if (this.files.length > 0) {
            if (this.files[0].type === 'audio/mpeg') {
                handleFiles(this.files);
            } else {
                logMessage('Ошибка: Пожалуйста, выберите MP3 файл.');
                this.value = '';
            }
        }
    });

    // Обработка выбранных файлов
    function handleFiles(files) {
        selectedFile = files[0];
        
        // Отображение информации о файле
        fileName.textContent = selectedFile.name;
        fileSize.textContent = (selectedFile.size / (1024 * 1024)).toFixed(2);
        fileInfo.style.display = 'block';
        
        // Активация кнопки обработки
        processBtn.disabled = false;
        
        logMessage(`Файл выбран: ${selectedFile.name} (${(selectedFile.size / (1024 * 1024)).toFixed(2)} МБ)`);
    }

    // Очистка выбранного файла
    clearFileBtn.addEventListener('click', function() {
        selectedFile = null;
        fileInput.value = '';
        fileInfo.style.display = 'none';
        processBtn.disabled = true;
        logMessage('Выбор файла очищен.');
    });

    // Обновление значений ползунков
    durationSlider.addEventListener('input', function() {
        durationValue.textContent = this.value;
    });

    windowSlider.addEventListener('input', function() {
        windowValue.textContent = this.value;
    });

    thresholdSlider.addEventListener('input', function() {
        thresholdValue.textContent = this.value;
    });

    minSilenceSlider.addEventListener('input', function() {
        minSilenceValue.textContent = this.value;
    });

    speedSlider.addEventListener('input', function() {
        speedValue.textContent = this.value;
    });

    // Изменение выходной директории
    changeOutputBtn.addEventListener('click', function() {
        const newPath = prompt('Введите путь для сохранения результатов:', outputPath.value);
        if (newPath !== null && newPath.trim() !== '') {
            outputPath.value = newPath.trim();
            logMessage(`Выходная директория изменена на: ${newPath.trim()}`);
        }
    });

    // Обработка файла
    processBtn.addEventListener('click', function() {
        if (!selectedFile) {
            logMessage('Ошибка: Файл не выбран.');
            return;
        }

        // Получение параметров
        const params = {
            duration: durationSlider.value,
            window: windowSlider.value,
            threshold: thresholdSlider.value,
            minSilence: minSilenceSlider.value,
            speed: speedSlider.value,
            outputDir: outputPath.value
        };

        // Отображение прогресс-бара
        progressContainer.style.display = 'block';
        progressBar.style.width = '0%';
        progressText.textContent = '0%';

        // Логирование начала обработки
        logMessage('Начало обработки файла...');
        logMessage(`Параметры: длительность=${params.duration}с, окно=${params.window}с, порог=${params.threshold}dB, мин.тишина=${params.minSilence}мс, скорость=${params.speed}x`);

        // Создание FormData для отправки файла
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('duration', params.duration);
        formData.append('window', params.window);
        formData.append('threshold', params.threshold);
        formData.append('minSilence', params.minSilence);
        formData.append('speed', params.speed);
        formData.append('outputDir', params.outputDir);

        // Имитация обработки (в реальном приложении здесь будет запрос к серверу)
        simulateProcessing(formData);
    });

    // Функция для обработки файла через API
    function simulateProcessing(formData) {
        processBtn.disabled = true;
        
        // Получаем параметры из formData для логирования
        const duration = formData.get('duration');
        const fileName = formData.get('file').name;
        
        // Начальный прогресс
        progressBar.style.width = '10%';
        progressText.textContent = '10%';
        logMessage(`Загрузка файла ${fileName}...`);
        
        // Отправка запроса на сервер
        fetch('/process', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Ошибка HTTP: ${response.status}`);
            }
            
            // Обновление прогресса во время обработки
            progressBar.style.width = '50%';
            progressText.textContent = '50%';
            logMessage(`Обработка файла на сервере...`);
            
            return response.json();
        })
        .then(data => {
            // Обработка успешного ответа
            progressBar.style.width = '100%';
            progressText.textContent = '100%';
            
            if (data.success) {
                logMessage(`Обработка завершена! ${data.message}`);
                
                // Добавление ссылок на скачивание файлов
                if (data.output_files && data.output_files.length > 0) {
                    logMessage('Созданные файлы:');
                    data.output_files.forEach(file => {
                        const fileLink = document.createElement('a');
                        fileLink.href = `/download/${file}`;
                        fileLink.textContent = file;
                        fileLink.target = '_blank';
                        fileLink.style.color = '#3498db';
                        
                        const logEntry = document.createElement('div');
                        logEntry.appendChild(document.createTextNode('- '));
                        logEntry.appendChild(fileLink);
                        
                        logOutput.appendChild(logEntry);
                    });
                    
                    // Автоматическая прокрутка лога вниз
                    logOutput.scrollTop = logOutput.scrollHeight;
                }
            } else {
                logMessage(`Ошибка: ${data.error || 'Неизвестная ошибка'}`);
            }
        })
        .catch(error => {
            // Обработка ошибок
            progressBar.style.width = '100%';
            progressText.textContent = 'Ошибка';
            logMessage(`Ошибка при обработке файла: ${error.message}`);
        })
        .finally(() => {
            // Разблокировка кнопки после завершения
            setTimeout(() => {
                processBtn.disabled = false;
            }, 2000);
        });
    }

    // Функция для добавления сообщений в лог
    function logMessage(message) {
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = `[${timestamp}] ${message}\n`;
        logOutput.textContent += logEntry;
        
        // Автоматическая прокрутка лога вниз
        logOutput.scrollTop = logOutput.scrollHeight;
    }

    // Инициализация с приветственным сообщением
    logMessage('MP3 AutoCut веб-интерфейс готов к работе. Выберите MP3 файл для начала.');
});