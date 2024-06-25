# Этот скрипт предназначен исключительно для релизов. Он позволяет избежать долгой задержки перед print(), а также предотвращает двойную загрузку библиотек в память.
# Для объеденения с main.exe используется Enigma Virutal Box
import os
import sys
import subprocess
import threading
import tempfile
import shutil
import hashlib
import win32gui

def Is_already_running():
    hwnd = win32gui.FindWindow(None, "WinYandexMusicRPC - Console")
    if hwnd:
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

        if Is_already_running():
            print("WinYandexMusicRPC is already running.")
            return
        
        current_path = os.path.dirname(os.path.abspath(sys.argv[0]))
        main_exe = os.path.join(current_path, "main.exe")
        
        if not os.path.exists(main_exe):
            raise FileNotFoundError(f"main.exe not found at {main_exe}")

        temp_dir_name = "WinYandexMusicRPC"
        temp_dir = os.path.join(tempfile.gettempdir(), temp_dir_name)

        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        temp_main_exe = os.path.join(temp_dir, "main.exe")

        if os.path.exists(temp_main_exe):
            main_exe_hash = Сalculate_file_hash(main_exe)
            temp_main_exe_hash = Сalculate_file_hash(temp_main_exe)
            if main_exe_hash != temp_main_exe_hash:
                os.remove(temp_main_exe)
                shutil.copy2(main_exe, temp_main_exe)

        first_pid = os.getpid()
        if Is_windows_11():
            subprocess.Popen(['start', '/min', 'conhost.exe', temp_main_exe, '--run-through-conhost', str(first_pid)] + sys.argv[1:], shell=True)
        else:
            subprocess.Popen(['cmd', '/c', 'start', '/min', 'cmd.exe', '/c', temp_main_exe, '--run-through-launcher', str(first_pid)] + sys.argv[1:], shell=True)
            
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
