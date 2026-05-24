import sys, traceback, os
os.chdir(r"D:\AI\jarvis-agent")
sys.path.insert(0, r"D:\AI\jarvis-agent")

log = open(r"C:\Temp\jarvis_test.txt", "w", encoding="utf-8")

def p(s):
    print(s)
    log.write(s + "\n")
    log.flush()

try:
    p("Step 1: importing Qt")
    from PyQt6.QtWidgets import QApplication
    p("Step 2: creating QApplication")
    app = QApplication(sys.argv)
    p("Step 3: importing ui")
    from ui import JarvisUI
    p("Step 4: creating JarvisUI")
    ui = JarvisUI("face.png")
    p("Step 5: WINDOW CREATED OK")
    import threading
    threading.Timer(4.0, app.quit).start()
    app.exec()
    p("Step 6: event loop exited")
except Exception as e:
    p(f"ERROR: {e}")
    traceback.print_exc(file=log)
    traceback.print_exc()
finally:
    log.close()
