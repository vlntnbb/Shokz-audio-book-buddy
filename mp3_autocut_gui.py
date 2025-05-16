import sys
import os
import subprocess
import threading
import json
from PyQt5 import QtWidgets, QtCore
import datetime

PROFILES_FILE = "profiles.json"
DEFAULT_PROFILE = {
    "input_dir": "source_mp3",
    "output_dir": "ready_mp3",
    "duration": 100,
    "window": 10,
    "threshold": -40,
    "min_silence": 500,
    "speed": 1.40
}

class Worker(QtCore.QThread):
    log_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal()

    def __init__(self, cmd):
        super().__init__()
        self.cmd = cmd
        self.process = None
        self._stop_event = threading.Event()

    def run(self):
        try:
            self.process = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        except Exception as e:
            self.log_signal.emit(f'Ошибка запуска: {e}')
            self.finished_signal.emit()
            return
        for line in self.process.stdout:
            self.log_signal.emit(line)
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
        self.setGeometry(100, 100, 800, 600)
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
        layout = QtWidgets.QVBoxLayout()

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
        layout.addLayout(profile_layout)

        # Сначала объявляем все поля
        self.input_dir = QtWidgets.QLineEdit()
        self.input_dir.setToolTip("Папка с исходными MP3-файлами. Поиск происходит рекурсивно, включая все подпапки. Пример: source_mp3")
        self.input_dir_btn = QtWidgets.QPushButton("...")
        self.input_dir_btn.setFixedWidth(30)
        self.input_dir_btn.clicked.connect(self.select_input_dir)
        input_dir_layout = QtWidgets.QHBoxLayout()
        input_dir_layout.addWidget(self.input_dir)
        input_dir_layout.addWidget(self.input_dir_btn)

        self.output_dir = QtWidgets.QLineEdit()
        self.output_dir.setToolTip("Папка для сохранения нарезанных MP3-файлов. Будет создана, если не существует. Пример: ready_mp3")
        self.output_dir_btn = QtWidgets.QPushButton("...")
        self.output_dir_btn.setFixedWidth(30)
        self.output_dir_btn.clicked.connect(self.select_output_dir)
        output_dir_layout = QtWidgets.QHBoxLayout()
        output_dir_layout.addWidget(self.output_dir)
        output_dir_layout.addWidget(self.output_dir_btn)

        self.copy_to_enabled = QtWidgets.QCheckBox("Копировать на внешний диск (copy-to)")
        self.copy_to_enabled.setToolTip("Если включено — после обработки все файлы будут скопированы на указанный внешний диск или папку (например, /Volumes/SHOKZ). После копирования исходные файлы могут быть перемещены в папку copied_mp3.")
        self.copy_to_enabled.stateChanged.connect(self.toggle_copy_to)
        self.copy_to = QtWidgets.QLineEdit()
        self.copy_to.setToolTip("Путь к папке/диску для копирования результата. Например: /Volumes/SHOKZ или D:/AUDIOBOOKS. Обязательно для режима копирования.")
        self.copy_to_btn = QtWidgets.QPushButton("...")
        self.copy_to_btn.setFixedWidth(30)
        self.copy_to_btn.clicked.connect(self.select_copy_to_dir)
        copy_to_layout = QtWidgets.QHBoxLayout()
        copy_to_layout.addWidget(self.copy_to)
        copy_to_layout.addWidget(self.copy_to_btn)
        self.copy_to_widget = QtWidgets.QWidget()
        self.copy_to_widget.setLayout(copy_to_layout)

        self.duration = QtWidgets.QSpinBox(); self.duration.setRange(10, 3600)
        self.duration.setToolTip("Желаемая длительность одного куска (секунды). Например, 100 — куски по ~1.5 минуты. Влияет на размер файлов и удобство навигации.")
        self.window = QtWidgets.QSpinBox(); self.window.setRange(1, 60)
        self.window.setToolTip("Окно поиска тишины (секунды, ± от точки разреза). Чем больше — тем выше шанс найти тишину, но обработка дольше.")
        self.threshold = QtWidgets.QSpinBox(); self.threshold.setRange(-80, 0)
        self.threshold.setToolTip("Порог тишины (dBFS). Чем ближе к 0 — тем менее тихие участки считаются тишиной. Обычно -40 оптимально.")
        self.min_silence = QtWidgets.QSpinBox(); self.min_silence.setRange(50, 10000)
        self.min_silence.setToolTip("Минимальная длина тишины (миллисекунды). Короткие паузы игнорируются. Например, 500 мс — только заметные паузы.")
        self.speed = QtWidgets.QDoubleSpinBox(); self.speed.setRange(0.5, 10.0); self.speed.setSingleStep(0.05)
        self.speed.setToolTip("Изменение скорости воспроизведения. 1.0 — без изменений, 1.4 — ускорить на 40%. Для atempo >2.0 возможны артефакты.")
        self.skip_existing = QtWidgets.QCheckBox("Пропускать уже обработанные")
        self.skip_existing.setToolTip("Если включено — файлы, для которых уже есть первый кусок в папке назначения, будут пропущены. Ускоряет повторную обработку.")
        self.copy_only = QtWidgets.QCheckBox("Только копировать/перемещать (без обработки)")
        self.copy_only.setToolTip("В этом режиме нарезка не выполняется, а только копирование/перемещение файлов из папки результатов на внешний диск и/или в папку copied_mp3.")
        self.copy_only.stateChanged.connect(self.toggle_processing_fields)
        self.tts_progress = QtWidgets.QCheckBox("Вставлять голосовое сообщение о прогрессе")
        self.tts_progress.setToolTip("В начало первого куска каждого файла будет вставлено голосовое сообщение: процент прослушанной книги и общая длительность. На Mac используется голос Yuri, на Win/Linux — pyttsx3.")

        # Теперь layout и форма
        form = QtWidgets.QFormLayout()
        form.addRow("Папка с исходными MP3", input_dir_layout)
        form.addRow("Папка для результатов", output_dir_layout)
        form.addRow("Длительность куска (сек)", self.duration)
        form.addRow("Окно поиска тишины (сек)", self.window)
        form.addRow("Порог тишины (dBFS)", self.threshold)
        form.addRow("Мин. длина тишины (мс)", self.min_silence)
        form.addRow("Скорость", self.speed)
        form.addRow(self.skip_existing)
        form.addRow(self.copy_only)
        form.addRow(self.copy_to_enabled)
        form.addRow("Папка для копирования (copy-to)", self.copy_to_widget)
        form.addRow(self.tts_progress)
        layout.addLayout(form)

        # Кнопки
        btn_layout = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("Запустить")
        self.stop_btn = QtWidgets.QPushButton("Остановить")
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        layout.addLayout(btn_layout)

        # Окно логов
        self.log_area = QtWidgets.QPlainTextEdit()
        self.log_area.setReadOnly(True)
        layout.addWidget(self.log_area)
        self.setLayout(layout)

        # Сигналы
        self.start_btn.clicked.connect(self.start_process)
        self.stop_btn.clicked.connect(self.stop_process)

        # Загружаем дефолтный профиль
        self.load_profile(self.profile_combo.currentText())

    def toggle_copy_to(self, state):
        self.copy_to_widget.setVisible(self.copy_to_enabled.isChecked())

    def load_profile(self, profile_name):
        p = self.profiles.get(profile_name, DEFAULT_PROFILE)
        self.input_dir.setText(p.get("input_dir", "source_mp3"))
        self.output_dir.setText(p.get("output_dir", "ready_mp3"))
        self.duration.setValue(p.get("duration", 100))
        self.window.setValue(p.get("window", 10))
        self.threshold.setValue(p.get("threshold", -40))
        self.min_silence.setValue(p.get("min_silence", 500))
        self.speed.setValue(p.get("speed", 1.40))
        self.copy_to.setText(p.get("copy_to", ""))
        self.copy_to_enabled.setChecked(p.get("copy_to_enabled", False))
        self.toggle_copy_to(None)
        self.tts_progress.setChecked(p.get("tts_progress", False))

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
                "tts_progress": self.tts_progress.isChecked()
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
        if not self.copy_only.isChecked():
            cmd += ["-d", str(self.duration.value())]
            cmd += ["-w", str(self.window.value())]
            cmd += ["-t", str(self.threshold.value())]
            cmd += ["-m", str(self.min_silence.value())]
            cmd += ["-s", str(self.speed.value())]
            if self.skip_existing.isChecked():
                cmd.append("--skip-existing")
        return cmd

    def start_process(self):
        self.log_area.clear()
        cmd = self.build_cmd()
        self.append_log(f'Запуск: {" ".join(cmd)}')
        self.worker = Worker(cmd)
        self.worker.log_signal.connect(self.append_log)
        self.worker.finished_signal.connect(self.on_finished)
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

    def on_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
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
        self.duration.setEnabled(enabled)
        self.window.setEnabled(enabled)
        self.threshold.setEnabled(enabled)
        self.min_silence.setEnabled(enabled)
        self.speed.setEnabled(enabled)
        self.tts_progress.setEnabled(enabled)
        self.skip_existing.setEnabled(enabled)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_()) 