# MP3 AutoCut — GUI and CLI Utility for Splitting MP3s

MP3 AutoCut is a program with a user-friendly graphical interface (GUI) that automatically divides long MP3 files (e.g., audiobooks, lectures, podcasts, voice recordings) into short, convenient parts. It searches for natural pauses (silence) and cuts the audio to avoid interrupting phrases. You can change the playback speed, and the finished files can be easily copied to an external drive — maintaining the correct order for listening on Shokz headphones. This is especially useful for Shokz, where you can't rewind 30-60 seconds: just cut the audio into short files and switch between them with a double or triple press on your Shokz.

For advanced users, command-line interface (CLI) operation is also available.

**The recommended way to install and run is through a virtual environment (venv).** This will ensure project dependency isolation and help avoid many common problems.

## Graphical User Interface (GUI)

The primary way to use the program is through the graphical interface. File: `mp3_autocut_gui.py`.

### GUI Features:
- All splitting and copying parameters are available through a convenient form.
- You can save and select setting profiles (e.g., for different scenarios).
- Profiles save all configured parameters, including checkbox states and normalization settings.
- Improved interface structure with grouped settings for better usability.
- Folder selection via dialog boxes.
- Copying to an external drive is optional (checkbox).
- Execution logs are displayed in real-time.
- Stop process button.
- Ability to set a custom application icon (see below).
- Everything works locally, cross-platform (Mac/Win/Linux).

## Features (Common to GUI and CLI)

- Recursive search and processing of all MP3s in a folder.
- Silence-based splitting with flexible parameters.
- Playback speed adjustment (0.5–2.0, experimentally up to 10).
- Peak volume normalization: each audio chunk can be normalized so that its loudest peak reaches a specified dBFS level (e.g., -0.1 dBFS). This helps to even out volume without clipping. Normalization is optional and configurable.
- File copying and moving with integrity check (SHA256).
- Insertion of voice progress messages (TTS, Mac/Win/Linux).
- Detailed operation logs.

## Requirements

- Python 3.6+ (Python 3.9+ recommended for better compatibility with dependencies).
- `ffmpeg` (must be in PATH).

## Installation and First Run (Recommended method — with venv)

1.  **Clone the repository or download the project files.**
    If you have Git installed:
    ```bash
    git clone https://github.com/YOUR_USERNAME/mp3-autocut-buddy.git # Replace with the actual repository URL
    cd mp3-autocut-buddy
    ```
    Or just download the ZIP archive and extract it.

2.  **Install `ffmpeg`:**
    -   macOS: `brew install ffmpeg`
    -   Ubuntu/Debian: `sudo apt update && sudo apt install ffmpeg`
    -   Windows: Download from the [official ffmpeg website](https://ffmpeg.org/download.html) and add the path to the `bin` folder (where `ffmpeg.exe` is located) to the system PATH variable.

3.  **Create and activate a virtual environment (venv):**
    In the root folder of the project (e.g., `mp3-autocut-buddy`), execute:
    ```bash
    python3 -m venv .venv_mp3autocut
    ```
    This command will create a `.venv_mp3autocut` folder with an isolated Python environment.
    Activate it:
    -   macOS / Linux:
        ```bash
        source .venv_mp3autocut/bin/activate
        ```
    -   Windows (Command Prompt):
        ```bash
        .venv_mp3autocut\Scripts\activate.bat
        ```
    -   Windows (PowerShell):
        ```bash
        .venv_mp3autocut\Scripts\Activate.ps1
        ```
    After activation, your command line prompt should change, indicating the active environment (e.g., `(.venv_mp3autocut) your-prompt$`).

4.  **Install project dependencies:**
    With the virtual environment activated, install all necessary libraries:
    ```bash
    python -m pip install -r requirements.txt
    ```
    Or simply `pip install -r requirements.txt` if `pip` is correctly associated with the venv.

5.  **Run the GUI:**
    Make sure the venv is still activated:
    ```bash
    python mp3_autocut_gui.py
    ```

## Typical Usage Scenario (with GUI and venv)

1.  Follow the steps in the "Installation and First Run" section.
2.  Ensure your virtual environment (`.venv_mp3autocut`) is activated.
3.  Run the GUI: `python mp3_autocut_gui.py`.
4.  In the interface, select the folder with the source MP3s (default is `source_mp3`).
5.  Configure the desired splitting parameters (chunk duration, speed, etc.) or select a saved profile.
6.  Click "Start."
7.  The processed chunks will be in the results folder (default is `ready_mp3`, folder structure is preserved).
8.  If needed, enable the "Copy to external drive" option and specify the path. Files will be copied and then moved from the results folder to `copied_mp3`.

## Command-Line Interface (CLI) Usage

For those who prefer the command line or want to automate the process, the `split_mp3.py` file is available. **Don't forget to activate the virtual environment before running!**

```bash
source .venv_mp3autocut/bin/activate  # macOS/Linux
# .venv_mp3autocut\Scripts\activate  # Windows
python split_mp3.py [parameters]
```

### Basic Processing (CLI)
```bash
python split_mp3.py
```
Normal splitting: all defaults (source_mp3 → ready_mp3, 100 sec, speed 1.0).

### Custom Parameters (CLI):
```bash
python split_mp3.py -i my_mp3s -o out_mp3s -d 300 -w 8 -t -35 -m 700 -s 1.25
```

### Copy and Move Only (CLI, no processing):
```bash
python split_mp3.py --copy-only --output-dir ready_mp3 --copy-to /Volumes/DRIVE
```

### All CLI Parameters:
- `-i, --input-dir` — folder with source MP3s (default: source_mp3)
- `-o, --output-dir` — folder for results (default: ready_mp3)
- `-d, --duration` — desired chunk duration, sec (default: 100)
- `-w, --window` — silence search window, sec (default: 10)
- `-t, --threshold` — silence threshold, dBFS (default: -40)
- `-m, --min-silence` — min. silence length, ms (default: 500, can be from 50)
- `-s, --speed` — speed factor (default: 1.0, range 0.5–10.0)
- `--skip-existing` — skip files if results already exist
- `--tts-progress` — insert voice progress message (percentage listened and total book duration; on Mac — Yuri voice, on Win/Linux — pyttsx3)
- `--copy-only` — only copy and move, do not process
- `--copy-to` — path for copying (required for --copy-only or for copying after processing in GUI/CLI)
- `--enable-normalization` — enable peak volume normalization.
- `--norm-dbfs` — target peak level for normalization in dBFS (used if `--enable-normalization` is on). Default: -0.1.

### CLI Command Examples

```bash
python split_mp3.py
```
Normal splitting: all defaults (source_mp3 → ready_mp3, 100 sec, speed 1.0).

```bash
python split_mp3.py -i audiobooks -o output -d 120 -w 10 -t -35 -m 1000
```
Split all mp3s from the `audiobooks` folder into 2-minute chunks, search for pauses of at least 1000 ms (1 sec) with a -35 dBFS threshold in a 10-sec window, results in the `output` folder.

```bash
python split_mp3.py -s 1.5
```
Speed up all mp3s by 1.5 times.

```bash
python split_mp3.py --skip-existing
```
Skip files if results already exist.

```bash
python split_mp3.py --copy-only --output-dir ready_mp3 --copy-to /Volumes/USB
```
Only copy all mp3s from the `ready_mp3` folder to the external drive `/Volumes/USB` with file integrity check (SHA256), then move them to the `copied_mp3` folder.

```bash
python split_mp3.py -i lectures -o chunks -d 120 -w 5 -t -45 -m 300 -s 0.8
```
Split all mp3s from the `lectures` folder into 2-minute chunks, search for pauses of at least 300 ms with a -45 dBFS threshold in a 5-sec window, slow down audio to 0.8x, results in the `chunks` folder.

```bash
python split_mp3.py --tts-progress
```
Insert a voice progress message at the beginning of the first chunk of each file.

```bash
python split_mp3.py --enable-normalization --norm-dbfs -0.5
```
Split files with default settings, enabling peak normalization to -0.5 dBFS.

```bash
python split_mp3.py -s 1.2 --enable-normalization
```
Speed up audio by 1.2 times and apply peak normalization with the default target level (-0.1 dBFS).

## Setting a Custom Application Icon (for GUI)

1.  Prepare an icon file. It is recommended to use `.png` format (e.g., `app_icon.png`)民主党 256x256 pixels or larger.
2.  Place the icon file (named `app_icon.png`) in the same directory as the `mp3_autocut_gui.py` script.
3.  The next time `mp3_autocut_gui.py` is launched, this icon will be used for the application window and in the Dock (on macOS).

## Notes
- For correct operation, `ffmpeg` must be installed and available in PATH.
- For TTS on Mac, the system voice Yuri (command `say`) is used; on Windows/Linux, the `pyttsx3` library is used (installed automatically with dependencies in venv).
- All main splitting and processing logic is in `split_mp3.py`, which is used by the GUI as well.
- All CLI parameters can also be viewed via `python split_mp3.py -h`.

## Troubleshooting

**1. Error `command not found: python`, `python3` or `pip`, `pip3`**
   - **Symptom:** The terminal does not recognize `python`, `python3`, `pip`, or `pip3` commands.
   - **Cause:**
     - Python is not installed, or its path is not added to the system PATH variable.
     - You are not in an activated virtual environment (venv) where these commands are available.
   - **Solution:**
     - **Using venv is recommended.** Ensure you have created and activated a venv according to the "Installation" section. In an activated venv, `python` and `pip` commands should work and point to the versions from the venv.
     - If you are NOT using venv (not recommended):
       - Ensure Python 3.6+ is installed. Check `python3 --version`. If not installed, download from the [official Python website](https://www.python.org/downloads/) and **make sure to check the "Add Python to PATH" option** or similar during installation.
       - On macOS and Linux, you often need to use `python3` and `pip3`.
       - If `pip` or `pip3` are not found, try: `python3 -m pip install --upgrade pip` to install/upgrade pip.

**2. Error `ModuleNotFoundError: No module named 'PyQt5'` (or `pydub`, `pyttsx3`)**
   - **Symptom:** When running a script (`mp3_autocut_gui.py` or `split_mp3.py`), an error occurs stating that a module is not found, e.g., `ModuleNotFoundError: No module named 'PyQt5'`.
   - **Cause:** Necessary libraries are not installed in the current Python environment (especially if venv is not activated or dependencies are not installed in it).
   - **Solution:**
     - Ensure your **virtual environment (venv) is activated**.
     - While in an activated venv, install all dependencies from the `requirements.txt` file:
       ```bash
       python -m pip install -r requirements.txt
       ```
     - If the error persists for a specific module, try reinstalling it explicitly (in an activated venv), e.g.:
       ```bash
       python -m pip uninstall PyQt5
       python -m pip install PyQt5
       ```

**3. Error `audioop` / `pydub` (especially on macOS/older Linux or with older Python versions)**
   - **Symptom:** Errors during import or operation of `pydub`, often mentioning `audioop`. May occur even when using venv if it was created based on an old Python version.
   - **Cause:** Incompatibility of older Python versions (usually before 3.8-3.9) with the `pydub` library.
   - **Solution:**
     - **Update Python and venv:** It is recommended to use Python 3.9+ (for macOS — Python 3.12 for best compatibility).
     - If you have a suitable Python version installed, but the venv was created earlier with an older version, or you want to ensure the correct Python version is used for the venv, create (or recreate) the virtual environment, explicitly specifying the Python interpreter:
       ```bash
       # Example for Python 3.12 (ensure python3.12 is available)
       python3.12 -m venv .venv_mp3autocut_py312 
       source .venv_mp3autocut_py312/bin/activate
       # Then install dependencies
       python -m pip install -r requirements.txt
       ```
       Replace `.venv_mp3autocut_py312` with the desired venv folder name and `python3.12` with your actual command for launching the required Python version (e.g., `python3.9`, `python3.10`, etc.). If you are unsure which command corresponds to the required version, check with `python3.X --version`.

**4. `ffmpeg` not found**
   - **Symptom:** Message "ffmpeg not found or not available in PATH" during file processing.
   - **Solution:** Follow the `ffmpeg` installation instructions in the "Installation and First Run" section. Restart the terminal/GUI after installation.

**5. Problems with MP3 decoding (`CouldntDecodeError`)**
   - **Symptom:** Log message "Error: Could not decode file..."
   - **Solution:** Check the integrity of the MP3 file, try opening it in another player.

**6. Low sound quality with significant speed changes**
   - **Symptom:** Sound distortions at speeds > 2.0x or < 0.5x.
   - **Solution:** For best quality, use speeds in the 0.5x-2.0x range.

**7. Problems with TTS (voice notifications)**
   - **Symptom:** Voice notifications do not work even though the option is enabled.
   - **Solution:**
     - **macOS:** Check the `say "hello"` command in the terminal. Ensure the `Yuri (Enhanced)` voice (or the default used) is available.
     - **Windows/Linux:** Ensure `pyttsx3` is installed in your venv. Check for TTS engines and voices in the operating system and their settings.

**8. "Freezing" when processing a large number of files**
   - **Symptom:** The program does not respond for a long time or shows no progress.
   - **Solution:** Be patient, especially with large volumes or on slower machines. Monitor the logs. For a test, try processing a smaller set of files.

**9. Copying to external drive does not work**
    - **Symptom:** Errors during copying, files do not appear on the drive.
    - **Solution:** Check the correctness of the path to the drive, its connection, available free space, and write permissions. 