import sys
import os
import subprocess
import threading
import json
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtGui import QIcon
import datetime

# Определяем абсолютный путь к директории, где лежит скрипт
# Это поможет правильно находить файл иконки, независимо от текущей рабочей директории
script_dir = os.path.dirname(os.path.abspath(__file__))
icon_path = os.path.join(script_dir, "app_icon.png")

PROFILES_FILE = "profiles.json"
DEFAULT_PROFILE = {
    "input_dir": "source_mp3",
    "output_dir": "ready_mp3",
    "duration": 100,
    "window": 10,
    "threshold": -40,
    "min_silence": 500,
    "speed": 1.40,
    "norm_dbfs": -0.1,
    "enable_normalization": False,
    "copy_only": False
}

class Worker(QtCore.QThread):
    log_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal()
    progress_signal = QtCore.pyqtSignal(int)  # Новый сигнал для прогресса

    def __init__(self, cmd):
        super().__init__()
        self.cmd = cmd
        self.process = None
        self._stop_event = threading.Event()
        self.total_files = 0
        self.processed_files = 0

    def run(self):
        # Сбрасываем счетчики при начале нового процесса
        self.total_files = 0
        self.processed_files = 0
        
        try:
            self.process = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        except Exception as e:
            self.log_signal.emit(f'Ошибка запуска: {e}')
            self.finished_signal.emit()
            return
        
        import re
        for line in self.process.stdout:
            self.log_signal.emit(line)
            
            # Отслеживаем количество найденных файлов
            if "Найдено" in line and "MP3 файлов для обработки" in line:
                match = re.search(r'Найдено (\d+) MP3 файлов', line)
                if match:
                    self.total_files = int(match.group(1))
                    self.progress_signal.emit(0)  # Сбрасываем прогресс в 0
                    
            # Отслеживаем завершение обработки файлов
            elif "--- Обработка файла" in line and "завершена ---" in line:
                self.processed_files += 1
                if self.total_files > 0:
                    progress = int((self.processed_files / self.total_files) * 100)
                    self.progress_signal.emit(progress)
            
            if self._stop_event.is_set():
                self.process.terminate()
                break
        self.process.wait()
        self.finished_signal.emit()

    def stop(self):
        self._stop_event.set()
        if self.process:
            self.process.terminate()

class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MP3 AutoCut GUI")
        self.setGeometry(100, 100, 800, 750)  # Оптимальная высота для большинства экранов
        
        # Устанавливаем иконку приложения
        icon = QIcon(icon_path)
        if not icon.isNull(): # Проверяем, успешно ли загрузилась иконка
            self.setWindowIcon(icon)
        else:
            # Если файл существует, но QIcon не смог его загрузить (например, битый файл)
            if os.path.exists(icon_path):
                QtWidgets.QMessageBox.warning(self, "Ошибка иконки", f"Не удалось загрузить файл иконки: {icon_path}\nПроверьте, что это корректный файл изображения (например, PNG).")
            else:
                # Если файл вообще не найден
                QtWidgets.QMessageBox.warning(self, "Ошибка иконки", f"Файл иконки не найден по пути: {icon_path}")
            
        self.worker = None
        self.profiles = {}
        self.init_profiles()
        self.init_ui()

    def init_profiles(self):
        # Загружаем профили из файла или создаём дефолтный
        if os.path.exists(PROFILES_FILE):
            with open(PROFILES_FILE, "r", encoding="utf-8") as f:
                self.profiles = json.load(f)
        else:
            self.profiles = {"Дефолт": DEFAULT_PROFILE}
            self.save_profiles()

    def save_profiles(self):
        with open(PROFILES_FILE, "w", encoding="utf-8") as f:
            json.dump(self.profiles, f, ensure_ascii=False, indent=2)

    def init_ui(self):
        main_layout = QtWidgets.QVBoxLayout()

        # --- Профили ---
        profile_layout = QtWidgets.QHBoxLayout()
        self.profile_combo = QtWidgets.QComboBox()
        self.profile_combo.addItems(self.profiles.keys())
        self.profile_combo.currentTextChanged.connect(self.load_profile)
        self.save_profile_btn = QtWidgets.QPushButton("Сохранить профиль")
        self.save_profile_btn.clicked.connect(self.save_current_profile)
        self.delete_profile_btn = QtWidgets.QPushButton("Удалить профиль")
        self.delete_profile_btn.clicked.connect(self.delete_current_profile)
        profile_layout.addWidget(QtWidgets.QLabel("Профиль:"))
        profile_layout.addWidget(self.profile_combo)
        profile_layout.addWidget(self.save_profile_btn)
        profile_layout.addWidget(self.delete_profile_btn)
        main_layout.addLayout(profile_layout)

        # --- Группа: Пути к папкам ---
        paths_group = QtWidgets.QGroupBox("Пути к папкам")
        paths_layout = QtWidgets.QFormLayout(paths_group)
        
        self.input_dir = QtWidgets.QLineEdit()
        self.input_dir.setToolTip("Папка с исходными MP3-файлами. Поиск происходит рекурсивно, включая все подпапки. Пример: source_mp3")
        self.input_dir_btn = QtWidgets.QPushButton("...")
        self.input_dir_btn.setFixedWidth(30)
        self.input_dir_btn.clicked.connect(self.select_input_dir)
        input_dir_h_layout = QtWidgets.QHBoxLayout()
        input_dir_h_layout.addWidget(self.input_dir)
        input_dir_h_layout.addWidget(self.input_dir_btn)
        paths_layout.addRow("Папка с исходными MP3:", input_dir_h_layout)

        self.output_dir = QtWidgets.QLineEdit()
        self.output_dir.setToolTip("Папка для сохранения нарезанных MP3-файлов. Будет создана, если не существует. Пример: ready_mp3")
        self.output_dir_btn = QtWidgets.QPushButton("...")
        self.output_dir_btn.setFixedWidth(30)
        self.output_dir_btn.clicked.connect(self.select_output_dir)
        output_dir_h_layout = QtWidgets.QHBoxLayout()
        output_dir_h_layout.addWidget(self.output_dir)
        output_dir_h_layout.addWidget(self.output_dir_btn)
        paths_layout.addRow("Папка для результатов:", output_dir_h_layout)
        main_layout.addWidget(paths_group)

        # --- Горизонтальный layout для двух групп настроек ---
        processing_groups_layout = QtWidgets.QHBoxLayout()

        # --- Группа: Основные параметры нарезки ---
        self.cutting_params_group = QtWidgets.QGroupBox("Основные параметры нарезки")
        cutting_layout = QtWidgets.QFormLayout(self.cutting_params_group)
        self.duration = QtWidgets.QSpinBox(); self.duration.setRange(10, 3600)
        self.duration.setToolTip("Желаемая длительность одного куска (в секундах). Например, 100 — куски по ~1.5 минуты. Если выбрана опция ускорения, то итоговая длительность куска будет пропорционально уменьшена. Влияет на удобство навигации по кнопкам следующий/предыдущий файл.")
        cutting_layout.addRow("Длительность куска (сек):", self.duration)
        self.window = QtWidgets.QSpinBox(); self.window.setRange(1, 60)
        self.window.setToolTip("Окно поиска тишины (секунды, ± от точки разреза). Чем больше — тем выше шанс найти тишину, но обработка дольше.")
        cutting_layout.addRow("Окно поиска тишины (сек):", self.window)
        self.threshold = QtWidgets.QSpinBox(); self.threshold.setRange(-80, 0)
        self.threshold.setToolTip("Порог тишины (dBFS). Чем ближе к 0 — тем менее тихие участки считаются тишиной. Обычно -40 оптимально.")
        cutting_layout.addRow("Порог тишины (dBFS):", self.threshold)
        self.min_silence = QtWidgets.QSpinBox(); self.min_silence.setRange(50, 10000)
        self.min_silence.setToolTip("Минимальная длина тишины (миллисекунды). Короткие паузы игнорируются. Например, 500 мс — только заметные паузы.")
        cutting_layout.addRow("Мин. длина тишины (мс):", self.min_silence)
        processing_groups_layout.addWidget(self.cutting_params_group)

        # --- Группа: Обработка аудио ---
        self.audio_processing_group = QtWidgets.QGroupBox("Обработка аудио")
        audio_layout = QtWidgets.QFormLayout(self.audio_processing_group)
        self.speed = QtWidgets.QDoubleSpinBox(); self.speed.setRange(0.5, 10.0); self.speed.setSingleStep(0.05)
        self.speed.setToolTip("Изменение скорости воспроизведения. 1.0 — без изменений, 1.4 — ускорить на 40%. Для atempo >2.0 возможны артефакты.")
        audio_layout.addRow("Скорость:", self.speed)

        # --- Компоновка элементов нормализации в одну строку ---
        normalization_layout = QtWidgets.QHBoxLayout()
        self.enable_normalization_checkbox = QtWidgets.QCheckBox("Включить нормализацию громкости")
        self.enable_normalization_checkbox.setToolTip("Если включено, громкость каждого куска будет нормализована до указанного уровня dBFS.")
        self.enable_normalization_checkbox.stateChanged.connect(self.toggle_norm_dbfs_field)
        normalization_layout.addWidget(self.enable_normalization_checkbox)

        self.norm_dbfs_label = QtWidgets.QLabel("Уровень (dBFS):") # Укоротил метку для компактности
        normalization_layout.addWidget(self.norm_dbfs_label)

        self.norm_dbfs = QtWidgets.QDoubleSpinBox(); self.norm_dbfs.setRange(-60.0, 0.0); self.norm_dbfs.setSingleStep(0.1); self.norm_dbfs.setDecimals(1)
        self.norm_dbfs.setToolTip("Целевой уровень нормализации громкости в dBFS. -0.1 dBFS - близко к максимуму. 0 dBFS - максимум. По умолчанию: -0.1.")
        normalization_layout.addWidget(self.norm_dbfs)
        normalization_layout.addStretch(1) # Растяжитель, чтобы прижать элементы влево

        audio_layout.addRow(normalization_layout)

        # Переносим TTS Progress сюда
        self.tts_progress = QtWidgets.QCheckBox("Вставлять голосовое сообщение о прогрессе")
        self.tts_progress.setToolTip("В начало первого куска каждого файла будет вставлено голосовое сообщение: процент прослушанной книги и общая длительность. На Mac используется голос Yuri, на Win/Linux — pyttsx3.")
        audio_layout.addRow(self.tts_progress) # Добавляем как новую строку в QFormLayout
        
        # Новый чекбокс для режима сетки TTS
        self.tts_progress_grid = QtWidgets.QCheckBox("Сообщение о прогрессе не чаще чем каждые 5%")
        self.tts_progress_grid.setToolTip("Если включено — голосовые сообщения о прогрессе будут вставляться не чаще чем каждые 5% (в точках 5%, 10%, 15%, 20% и т.д.). Первое сообщение появится только после 5% прогресса.")
        audio_layout.addRow(self.tts_progress_grid)

        processing_groups_layout.addWidget(self.audio_processing_group)

        main_layout.addLayout(processing_groups_layout)

        # --- Группа: Операции с файлами и опции ---
        self.file_ops_group = QtWidgets.QGroupBox("Операции с файлами и опции")
        file_ops_layout = QtWidgets.QVBoxLayout(self.file_ops_group)
        file_ops_layout.setContentsMargins(10, 10, 10, 5)  # Уменьшаем нижний отступ
        file_ops_layout.setSpacing(4)  # Уменьшаем интервал между опциями

        # Чекбокс "Пропускать уже обработанные"
        self.skip_existing = QtWidgets.QCheckBox("Пропускать уже обработанные")
        self.skip_existing.setToolTip("Если включено — файлы, для которых уже есть первый кусок в папке назначения, будут пропущены. Ускоряет повторную обработку.")
        file_ops_layout.addWidget(self.skip_existing)
        
        # Чекбокс "Только копировать/перемещать"
        self.copy_only = QtWidgets.QCheckBox("Только копировать/перемещать (без обработки)")
        self.copy_only.setToolTip("В этом режиме нарезка не выполняется, а только копирование/перемещение файлов из папки результатов на внешний диск и/или в папку copied_mp3.")
        self.copy_only.stateChanged.connect(self.toggle_processing_fields)
        file_ops_layout.addWidget(self.copy_only)

        # Компактный layout для копирования на внешний диск
        copy_to_layout = QtWidgets.QVBoxLayout()
        copy_to_layout.setSpacing(2)
        
        self.copy_to_enabled = QtWidgets.QCheckBox("Копировать на внешний диск (copy-to)")
        self.copy_to_enabled.setToolTip("Если включено — после обработки все файлы будут скопированы на указанный внешний диск или папку (например, /Volumes/SHOKZ). После копирования исходные файлы могут быть перемещены в папку copied_mp3.")
        self.copy_to_enabled.stateChanged.connect(self.toggle_copy_to_visibility)
        copy_to_layout.addWidget(self.copy_to_enabled)

        # Поле ввода пути для copy-to
        copy_to_path_layout = QtWidgets.QHBoxLayout()
        copy_to_path_layout.setContentsMargins(20, 0, 0, 0)  # Отступ слева для визуальной связи с чекбоксом
        
        self.copy_to = QtWidgets.QLineEdit()
        self.copy_to.setToolTip("Путь к папке/диску для копирования результата. Например: /Volumes/SHOKZ или D:/AUDIOBOOKS. Обязательно для режима копирования.")
        copy_to_path_layout.addWidget(self.copy_to)

        self.copy_to_btn = QtWidgets.QPushButton("...")
        self.copy_to_btn.setFixedWidth(30)
        self.copy_to_btn.clicked.connect(self.select_copy_to_dir)
        copy_to_path_layout.addWidget(self.copy_to_btn)
        
        copy_to_layout.addLayout(copy_to_path_layout)
        file_ops_layout.addLayout(copy_to_layout)
        
        # Устанавливаем максимальную высоту для группы чтобы не растягивалась
        self.file_ops_group.setMaximumHeight(120)
        main_layout.addWidget(self.file_ops_group)
        
        # Кнопки
        btn_layout = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("Запустить")
        self.stop_btn = QtWidgets.QPushButton("Остановить")
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        main_layout.addLayout(btn_layout)

        # Прогресс бар
        progress_layout = QtWidgets.QVBoxLayout()
        progress_label = QtWidgets.QLabel("Прогресс обработки:")
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v% (%p%)")  # Показывает и текущее значение и процент
        progress_layout.addWidget(progress_label)
        progress_layout.addWidget(self.progress_bar)
        main_layout.addLayout(progress_layout)

        # Окно логов
        self.log_area = QtWidgets.QPlainTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMinimumHeight(200)  # Уменьшаем минимальную высоту
        main_layout.addWidget(self.log_area, 1)  # Добавляем stretch factor = 1, чтобы заняло всё доступное место
        self.setLayout(main_layout)

        # Сигналы
        self.start_btn.clicked.connect(self.start_process)
        self.stop_btn.clicked.connect(self.stop_process)

        # Загружаем дефолтный профиль
        self.load_profile(self.profile_combo.currentText())
        self.toggle_copy_to_visibility()

    def toggle_copy_to_visibility(self):
        is_checked = self.copy_to_enabled.isChecked()
        # Просто управляем активностью поля и кнопки
        self.copy_to.setEnabled(is_checked) 
        self.copy_to_btn.setEnabled(is_checked)

    def load_profile(self, profile_name):
        p = self.profiles.get(profile_name, DEFAULT_PROFILE)
        self.input_dir.setText(p.get("input_dir", "source_mp3"))
        self.output_dir.setText(p.get("output_dir", "ready_mp3"))
        self.duration.setValue(p.get("duration", 100))
        self.window.setValue(p.get("window", 10))
        self.threshold.setValue(p.get("threshold", -40))
        self.min_silence.setValue(p.get("min_silence", 500))
        self.speed.setValue(p.get("speed", 1.40))
        self.norm_dbfs.setValue(p.get("norm_dbfs", DEFAULT_PROFILE["norm_dbfs"]))
        self.enable_normalization_checkbox.setChecked(p.get("enable_normalization", DEFAULT_PROFILE["enable_normalization"]))
        self.toggle_norm_dbfs_field()
        self.copy_to.setText(p.get("copy_to", ""))
        self.copy_to_enabled.setChecked(p.get("copy_to_enabled", False))
        self.tts_progress.setChecked(p.get("tts_progress", False))
        self.tts_progress_grid.setChecked(p.get("tts_progress_grid", False))
        self.skip_existing.setChecked(p.get("skip_existing", False))
        self.copy_only.setChecked(p.get("copy_only", DEFAULT_PROFILE.get("copy_only", False)))
        self.toggle_processing_fields(None)
        self.toggle_copy_to_visibility()

    def save_current_profile(self):
        current_name = self.profile_combo.currentText()
        name, ok = QtWidgets.QInputDialog.getText(self, "Сохранить профиль", "Имя профиля:", text=current_name)
        if ok and name:
            if name in self.profiles:
                reply = QtWidgets.QMessageBox.question(
                    self,
                    "Перезаписать профиль",
                    f"Перезаписать профиль '{name}'?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
                )
                if reply != QtWidgets.QMessageBox.Yes:
                    return
            self.profiles[name] = {
                "input_dir": self.input_dir.text(),
                "output_dir": self.output_dir.text(),
                "duration": self.duration.value(),
                "window": self.window.value(),
                "threshold": self.threshold.value(),
                "min_silence": self.min_silence.value(),
                "speed": self.speed.value(),
                "copy_to": self.copy_to.text(),
                "copy_to_enabled": self.copy_to_enabled.isChecked(),
                "tts_progress": self.tts_progress.isChecked(),
                "tts_progress_grid": self.tts_progress_grid.isChecked(),
                "norm_dbfs": self.norm_dbfs.value(),
                "enable_normalization": self.enable_normalization_checkbox.isChecked(),
                "skip_existing": self.skip_existing.isChecked(),
                "copy_only": self.copy_only.isChecked()
            }
            self.save_profiles()
            self.profile_combo.blockSignals(True)
            self.profile_combo.clear()
            self.profile_combo.addItems(self.profiles.keys())
            self.profile_combo.setCurrentText(name)
            self.profile_combo.blockSignals(False)

    def delete_current_profile(self):
        name = self.profile_combo.currentText()
        if name == "Дефолт":
            QtWidgets.QMessageBox.warning(self, "Удаление профиля", "Нельзя удалить дефолтный профиль!")
            return
        reply = QtWidgets.QMessageBox.question(self, "Удалить профиль", f"Удалить профиль '{name}'?", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.Yes:
            self.profiles.pop(name, None)
            self.save_profiles()
            self.profile_combo.blockSignals(True)
            self.profile_combo.clear()
            self.profile_combo.addItems(self.profiles.keys())
            self.profile_combo.setCurrentText("Дефолт")
            self.profile_combo.blockSignals(False)
            self.load_profile("Дефолт")

    def build_cmd(self):
        cmd = [sys.executable, "-u", "split_mp3.py"]
        if self.copy_only.isChecked():
            cmd.append("--copy-only")
        if self.input_dir.text():
            cmd += ["-i", self.input_dir.text()]
        if self.output_dir.text():
            cmd += ["-o", self.output_dir.text()]
        if self.copy_to_enabled.isChecked() and self.copy_to.text():
            cmd += ["--copy-to", self.copy_to.text()]
        if self.tts_progress.isChecked():
            cmd.append("--tts-progress")
        if self.tts_progress_grid.isChecked():
            cmd.append("--tts-progress-grid")
        if not self.copy_only.isChecked():
            cmd += [
                "-d", str(self.duration.value()),
                "-w", str(self.window.value()),
                "-t", str(self.threshold.value()),
                "-m", str(self.min_silence.value()),
                "-s", str(self.speed.value()),
            ]
            if self.skip_existing.isChecked():
                cmd.append("--skip-existing")
            if self.enable_normalization_checkbox.isChecked():
                cmd.append("--enable-normalization")
                cmd.extend(["--norm-dbfs", str(self.norm_dbfs.value())])

        return cmd

    def start_process(self):
        self.log_area.clear()
        self.progress_bar.setValue(0)  # Сбрасываем прогресс бар
        cmd = self.build_cmd()
        self.append_log(f'Запуск: {" ".join(cmd)}')
        self.worker = Worker(cmd)
        self.worker.log_signal.connect(self.append_log)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.progress_signal.connect(self.update_progress)  # Подключаем сигнал прогресса
        self.worker.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def stop_process(self):
        if self.worker:
            self.worker.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def append_log(self, text):
        for line in text.rstrip().splitlines():
            ts = datetime.datetime.now().strftime('%H:%M:%S')
            self.log_area.appendPlainText(f'[{ts}] {line}')

    def update_progress(self, value):
        """Обновляет прогресс бар"""
        self.progress_bar.setValue(value)

    def on_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setValue(100)  # Завершаем прогресс на 100%
        self.append_log("\n=== Готово ===\n")

    def select_input_dir(self):
        dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Выбери папку с исходными MP3")
        if dir:
            self.input_dir.setText(dir)

    def select_output_dir(self):
        dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Выбери папку для результатов")
        if dir:
            self.output_dir.setText(dir)

    def select_copy_to_dir(self):
        dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Выбери папку для копирования (copy-to)")
        if dir:
            self.copy_to.setText(dir)

    def toggle_processing_fields(self, state):
        enabled = not self.copy_only.isChecked()
        self.cutting_params_group.setEnabled(enabled)
        self.audio_processing_group.setEnabled(enabled)
        self.tts_progress.setEnabled(enabled)
        self.tts_progress_grid.setEnabled(enabled)
        self.skip_existing.setEnabled(enabled)
        if enabled:
            self.toggle_norm_dbfs_field()

    def toggle_norm_dbfs_field(self):
        is_checked = self.enable_normalization_checkbox.isChecked()
        self.norm_dbfs.setEnabled(is_checked)
        self.norm_dbfs_label.setEnabled(is_checked) # Управляем активностью метки

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)

    # Определяем абсолютный путь к директории, где лежит скрипт
    script_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(script_dir, "app_icon.png")
    print(f"[DEBUG] Путь к иконке: {icon_path}")
    print(f"[DEBUG] Файл иконки существует: {os.path.exists(icon_path)}")

    app_icon = QIcon(icon_path)
    if app_icon.isNull():
        print("[DEBUG] QIcon для приложения не смогла загрузить иконку.")
        if os.path.exists(icon_path):
            # Это предупреждение может не отобразиться до запуска event loop, 
            # но мы пытаемся его показать как можно раньше.
            QtWidgets.QMessageBox.warning(None, "Ошибка иконки", f"Не удалось загрузить файл иконки для приложения: {icon_path}\nПроверьте, что это корректный файл изображения (например, PNG).")
        else:
            QtWidgets.QMessageBox.warning(None, "Ошибка иконки", f"Файл иконки для приложения не найден: {icon_path}")
    else:
        print("[DEBUG] QIcon для приложения успешно создана.")
        app.setWindowIcon(app_icon) # <--- Устанавливаем иконку для QApplication

    window = MainWindow() # <--- MainWindow создается ПОСЛЕ установки иконки для app
    window.show()
    sys.exit(app.exec_()) 