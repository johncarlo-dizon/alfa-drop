import tkinter as tk
from tkinter import messagebox, ttk

import theme as T
from stores import read_stores_raw, write_stores_raw

HINT = ("A line with just a name starts a group (DC). Under it, one store per line:   "
        "ip, username, password, name, code, pos")


def open_stores_editor(parent, on_save=None):
    """Open the stores.txt editor. on_save() is called after each successful save.
    Returns the window; win.request_close() closes it (asking about unsaved changes first)."""
    win = tk.Toplevel(parent)
    win.title("Edit stores.txt")
    win.configure(bg=T.BG)
    win.transient(parent)

    # centred over the main window, never closer than 16 px to a screen edge
    parent.update_idletasks()
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    w, h = min(800, sw - 64), min(540, sh - 120)
    x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
    x = max(16, min(x, sw - w - 16))
    y = max(16, min(y, sh - h - 64))
    win.geometry(f"{w}x{h}+{x}+{y}")
    win.minsize(560, 360)

    win.grid_columnconfigure(0, weight=1)
    win.grid_rowconfigure(1, weight=1)

    # ---- header
    head = ttk.Frame(win, padding=(20, 16, 20, 8))
    head.grid(row=0, column=0, sticky="ew")
    ttk.Label(head, text="Store list", font=("Segoe UI", 13, "bold")).pack(anchor="w")
    ttk.Label(head, text=HINT, style="Subtitle.TLabel", wraplength=w - 60,
              justify="left").pack(anchor="w", pady=(2, 0))

    # ---- editor
    border = tk.Frame(win, bg=T.BORDER)
    border.grid(row=1, column=0, sticky="nsew", padx=20, pady=(4, 0))
    inner = tk.Frame(border, bg=T.FIELD)
    inner.pack(fill="both", expand=True, padx=1, pady=1)
    inner.grid_rowconfigure(0, weight=1)
    inner.grid_columnconfigure(0, weight=1)

    text = tk.Text(inner, font=("Consolas", 10), wrap="none", undo=True, bg=T.FIELD, fg=T.TEXT,
                   insertbackground=T.TEXT, selectbackground=T.ACCENT_SOFT,
                   selectforeground=T.TEXT, relief="flat", bd=0, highlightthickness=0,
                   padx=10, pady=8)
    vbar = ttk.Scrollbar(inner, orient="vertical", command=text.yview)
    hbar = ttk.Scrollbar(inner, orient="horizontal", command=text.xview)
    text.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
    text.grid(row=0, column=0, sticky="nsew")
    vbar.grid(row=0, column=1, sticky="ns")
    hbar.grid(row=1, column=0, sticky="ew")

    saved = {"text": read_stores_raw().rstrip("\n")}
    text.insert("1.0", saved["text"])
    text.edit_reset()                      # no undo back past the loaded text

    # ---- bottom bar
    bar = ttk.Frame(win, padding=(20, 12, 20, 16))
    bar.grid(row=2, column=0, sticky="ew")
    status = tk.Label(bar, text="", bg=T.BG, font=T.FONT_SMALL)
    status.pack(side="left")

    def is_dirty():
        return text.get("1.0", "end-1c") != saved["text"]

    def refresh_status(just_saved=False):
        if is_dirty():
            status.config(text="●  Unsaved changes", fg=T.WARNING)
        elif just_saved:
            status.config(text="✓  Saved — store list reloaded", fg=T.SUCCESS)
        else:
            status.config(text="No changes", fg=T.MUTED)

    def save(_event=None):
        content = text.get("1.0", "end-1c")
        try:
            write_stores_raw(content)
        except OSError as e:
            messagebox.showerror("Save failed", f"Could not save stores.txt:\n{e}", parent=win)
            return "break"
        saved["text"] = content.rstrip("\n")
        if on_save:
            on_save()
        refresh_status(just_saved=True)
        return "break"

    def request_close(_event=None):
        if is_dirty():
            answer = messagebox.askyesnocancel(
                "Unsaved changes", "Save your changes to stores.txt before closing?", parent=win)
            if answer is None:
                return False
            if answer:
                save()
                if is_dirty():            # the save failed
                    return False
        win.destroy()
        return True

    ttk.Button(bar, text="Close", style="Ghost.TButton",
               command=request_close).pack(side="right", padx=(8, 0))
    save_btn = ttk.Button(bar, text="💾  Save", style="Success.TButton", command=save)
    save_btn.pack(side="right")

    def on_modified(_event=None):
        if text.edit_modified():
            refresh_status()
            text.edit_modified(False)

    text.bind("<<Modified>>", on_modified)
    win.bind("<Control-s>", save)
    win.bind("<Escape>", request_close)
    win.protocol("WM_DELETE_WINDOW", request_close)
    win.request_close = request_close

    refresh_status()
    text.focus_set()
    return win