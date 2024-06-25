# Этот скрипт предназначен исключительно для релизов. Он позволяет избежать долгой задержки перед print(), а также предотвращает двойную загрузку библиотек в память.
# Для объеденения с main.exe используется Enigma Virutal Box
import os
import sys
import subprocess
import threading

def Is_windows_11():
    return sys.getwindowsversion().build >= 22000

def main():
    try:
        current_path = os.path.dirname(os.path.abspath(sys.argv[0]))
        main_exe = os.path.join(current_path, "main.exe")
        
        if not os.path.exists(main_exe):
            raise FileNotFoundError(f"main.exe not found at {main_exe}")

        print("Wait a few seconds for the script to load...")
        first_pid = os.getpid()

        if Is_windows_11(): 
            subprocess.Popen(['start', '/min', 'conhost.exe', main_exe, '--run-through-conhost', str(first_pid)] + sys.argv[1:], shell=True)
        else:
            subprocess.Popen(['cmd', '/c', 'start', '/min', 'cmd.exe', '/c', main_exe, '--run-through-launcher', str(first_pid)] + sys.argv[1:], shell=True)

        event = threading.Event()
        event.wait()
    except Exception as exception:
        print(f"Something happened when trying to load: {exception}")

if __name__ == "__main__":
    main()
