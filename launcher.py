# Этот скрипт предназначен исключительно для релизов. Он позволяет избежать долгой задержки перед print(), а также предотвращает двойную загрузку библиотек в память.
# Для компиляции с main.exe используется "pyinstaller --clean launcher.spec"
import os
import sys
import threading
import tempfile
import shutil
import hashlib
import psutil
import win32console

def Set_ConsoleMode():
    hStdin = win32console.GetStdHandle(win32console.STD_INPUT_HANDLE)
    mode = hStdin.GetConsoleMode()
    # Отключить ENABLE_QUICK_EDIT_MODE, чтобы запретить выделение текста
    new_mode = mode & ~0x0040
    hStdin.SetConsoleMode(new_mode)

def Is_already_running(executable_name):
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] == executable_name:
            return True
    return False

def Is_windows_11():
    return sys.getwindowsversion().build >= 22000

def Сalculate_file_hash(file_path):
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def main():
    try:
        print("Initialize...")
        Set_ConsoleMode()
        
        current_path = sys._MEIPASS
        main_exe = os.path.join(current_path, "main.exe")
        
        if not os.path.exists(main_exe):
            raise FileNotFoundError(f"main.exe not found at {main_exe}")

        temp_dir_name = "WinYandexMusicRPC"
        temp_dir = os.path.join(tempfile.gettempdir(), temp_dir_name)

        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        temp_main_exe = os.path.join(temp_dir, "WinYandexMusicRPC.exe")
        
        if os.path.exists(temp_main_exe):
            if Is_already_running("WinYandexMusicRPC.exe"):
                print("WinYandexMusicRPC is already running.")
                return
            main_exe_hash = Сalculate_file_hash(main_exe)
            temp_main_exe_hash = Сalculate_file_hash(temp_main_exe)
            if main_exe_hash != temp_main_exe_hash:
                os.remove(temp_main_exe)
                shutil.copy2(main_exe, temp_main_exe)
        else:
            shutil.copy2(main_exe, temp_main_exe)

        first_pid = os.getpid()
        if Is_windows_11():
            os.system(f'start /min conhost.exe {temp_main_exe} --run-through-conhost {first_pid} {" ".join(sys.argv[1:])}')
        else:
            os.system(f'cmd /c start /min cmd.exe /c {temp_main_exe} --run-through-launcher {first_pid} {" ".join(sys.argv[1:])}')
            
        print("Wait a few seconds for the script to load...")
        event = threading.Event()
        event.wait()
    except PermissionError as e:
        print(f"Permission error: {e}")
    except Exception as exception:
        print(f"Something happened when trying to load: {exception}")

if __name__ == "__main__":
    main()
    input("Press any key to exit...")
