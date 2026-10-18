import os
import tkinter as tk

from app import AlfaDropApp
from config import RESOURCE_DIR


def main():
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