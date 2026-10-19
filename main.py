import os
import tkinter as tk

from app import AlfaDropApp
from config import RESOURCE_DIR


def main():
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Alfamart.AlfaDrop")
    except Exception:
        pass
    root = tk.Tk()
    icon = os.path.join(RESOURCE_DIR, "assets", "alfadrop.ico")   # optional
    if os.path.exists(icon):
        try:
            root.iconbitmap(icon)
        except Exception:
            pass
    AlfaDropApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()