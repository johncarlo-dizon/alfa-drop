import os
import queue
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from editor import open_stores_editor
import theme as T
from config import (
    APP_NAME, APP_SUBTITLE, DEFAULT_REMOTE_DIR, DEFAULT_WORKERS, LOG_FILE, LOG_MAX_BYTES,
    LOG_PANEL_MAX_LINES, MAX_WORKERS, STORES_FILE,
)
from deployer import ICON, LABEL, fmt_size, start_deployment
from stores import load_stores

PAD_X, PAD_Y = 28, 14         # gap between the content and the window edge
SCREEN_GAP = 16               # minimum gap between the window and the screen / taskbar edge
MAX_CONTENT_W, MAX_CONTENT_H = 1060, 720   # on a big window the content stays centred at this size
RULE = "=" * 52
POLL_BATCH = 400


def fmt_elapsed(seconds):
    seconds = int(round(seconds))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def store_key(store):
    return (store["ip"], store.get("code", ""), store.get("pos", ""))


def write_log_file(lines):
    """Best-effort append of (text, level) lines to the log file."""
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) >= LOG_MAX_BYTES:
            os.replace(LOG_FILE, LOG_FILE + ".old")
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            for text, level in lines:
                f.write(f"[{stamp}] {level:<5} {text}\n")
    except Exception:
        pass


def level_of(tag):
    return {"failed": "ERROR", "cancelled": "WARN"}.get(tag, "INFO")


class AlfaDropApp:
    def __init__(self, root):
        self.root = root
        root.title(f"{APP_NAME} — {APP_SUBTITLE}")
        T.apply_style(root)

        self.stores, self.store_warnings = load_stores()
        self.selected = set()          # indexes into self.stores
        self.row_to_idx = {}           # tree item id -> store index
        self.group_children = {}       # tree group id -> [store index]
        self.group_names = {}
        self.files = []                # [{"path", "name"}]
        self.log_queue = queue.Queue()
        self.cancel_event = None
        self.cancelling = False
        self.results = []
        self.counts = {}
        self.run_total = 0
        self.run_started = None
        self.step_text = ""
        self.failed_keys = []
        self._filter_job = None
        self._editor = None

        self.replace_var = tk.BooleanVar(value=True)
        self.force_var = tk.BooleanVar(value=False)
        self.remote_dir_var = tk.StringVar(value=DEFAULT_REMOTE_DIR)
        self.workers_var = tk.StringVar(value=str(DEFAULT_WORKERS))
        self.search_var = tk.StringVar()

        self._build()
        self._rebuild_tree()
        self._refresh_files()
        self._update_summary()
        self._place_window()      # last: needs the finished layout to know the height it needs
        self._log("Ready. Add files, tick the store PCs, then press Deploy.", "muted")
        for w in self.store_warnings:
            self._log(f"⚠ {w}", "cancelled")
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------ window
    def _work_area(self):
        """(left, top, right, bottom) of the screen without the taskbar."""
        try:
            import ctypes
            from ctypes import wintypes
            rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
                return rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def _place_window(self):
        """Centre the window in the usable screen area (above the taskbar), with a gap on every side."""
        r = self.root
        r.update_idletasks()
        left, top, right, bottom = self._work_area()
        area_w, area_h = right - left, bottom - top
        deco_w = 16                                                   # side borders
        deco_h = max(r.winfo_rooty() - r.winfo_y(), 31) + 8           # title bar + bottom border
        need_h = self.content.winfo_reqheight() + 2 * PAD_Y
        w = min(1120, area_w - 2 * SCREEN_GAP - deco_w)
        h = min(max(need_h, 560), area_h - 2 * SCREEN_GAP - deco_h)
        x = left + (area_w - (w + deco_w)) // 2
        y = top + (area_h - (h + deco_h)) // 2
        r.geometry(f"{w}x{h}+{x}+{y}")
        r.minsize(min(960, w), min(520, h))

    def _on_resize(self, event):
        if event.widget is self.root:
            width = min(MAX_CONTENT_W, event.width - 2 * PAD_X)
            height = min(MAX_CONTENT_H, event.height - 2 * PAD_Y)
            self.content.place_configure(width=max(width, 400), height=max(height, 300))

    def _on_close(self):
        if self.cancel_event is not None and not self.cancel_event.is_set():
            if not messagebox.askyesno("Deployment running",
                                       "A deployment is still running. Stop it and close AlfaDrop?"):
                return
            self.cancel_event.set()
        if self._editor is not None and self._editor.winfo_exists():
            if not self._editor.request_close():
                return
        self.root.destroy()

    # ---------------------------------------------------------- building
    def _card(self, parent, title=None):
        outer = tk.Frame(parent, bg=T.BORDER)
        inner = ttk.Frame(outer, style="Card.TFrame", padding=(14, 10))
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        header = None
        if title:
            header = ttk.Frame(inner, style="Card.TFrame")
            header.pack(fill="x", pady=(0, 8))
            ttk.Label(header, text=title, style="CardTitle.TLabel").pack(side="left")
        return outer, inner, header

    def _build(self):
        r = self.root
        # One content block, centred horizontally and vertically in the window.
        self.content = ttk.Frame(r)
        self.content.place(relx=0.5, rely=0.5, anchor="center", width=900, height=600)
        r.bind("<Configure>", self._on_resize)

        c = self.content
        c.grid_columnconfigure(0, weight=1, uniform="col")
        c.grid_columnconfigure(1, weight=1, uniform="col")
        c.grid_rowconfigure(1, weight=1, minsize=370)

        header = ttk.Frame(c)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(header, text=APP_NAME, style="Title.TLabel", anchor="center").pack(fill="x")
        ttk.Label(header, text="Send files to your store PCs and see the result for each one",
                  style="Subtitle.TLabel", anchor="center").pack(fill="x")

        left = ttk.Frame(c)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        left.grid_columnconfigure(0, weight=1)
        right = ttk.Frame(c)
        right.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        right.grid_columnconfigure(0, weight=1)

        self._build_files(left)
        self._build_options(left)
        self._build_stores(right)
        self._build_log(right)
        self._build_deploy(c)          # full-width bar at the bottom

    def _build_files(self, parent):
        outer, body, _h = self._card(parent, "1  ·  Files to deploy")
        outer.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        parent.grid_rowconfigure(0, weight=1, minsize=165)

        btns = ttk.Frame(body, style="Card.TFrame")
        btns.pack(fill="x", pady=(0, 8))
        add_btn = ttk.Button(btns, text="Add Files", style="Accent.TButton",
                             command=self.choose_files)
        add_btn.pack(side="left")
        remove_btn = ttk.Button(btns, text="Remove", style="Ghost.TButton",
                                command=self.remove_selected)
        remove_btn.pack(side="left", padx=(8, 0))
        clear_btn = ttk.Button(btns, text="Clear All", style="Ghost.TButton",
                               command=self.clear_files)
        clear_btn.pack(side="left", padx=(8, 0))
        T.add_tooltip(add_btn, "Choose one or more files from this computer")
        T.add_tooltip(remove_btn, "Remove the highlighted files from the list")
        T.add_tooltip(clear_btn, "Remove every file from the list")

        box = tk.Frame(body, bg=T.BORDER)
        box.pack(fill="both", expand=True)
        box_in = tk.Frame(box, bg=T.FIELD)
        box_in.pack(fill="both", expand=True, padx=1, pady=1)
        self.files_listbox = tk.Listbox(
            box_in, height=4, selectmode="extended", font=T.FONT, bg=T.FIELD, fg=T.TEXT,
            relief="flat", bd=0, highlightthickness=0, selectbackground=T.ACCENT_SOFT,
            selectforeground=T.TEXT, activestyle="none")
        sb = ttk.Scrollbar(box_in, orient="vertical", command=self.files_listbox.yview)
        self.files_listbox.configure(yscrollcommand=sb.set)
        self.files_listbox.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=4)
        sb.pack(side="right", fill="y")
        self.files_empty = tk.Label(box_in, text="No files yet — click “Add Files”",
                                    bg=T.FIELD, fg=T.MUTED, font=T.FONT)
        self.files_info = ttk.Label(body, text="", style="Hint.TLabel")
        self.files_info.pack(anchor="w", pady=(6, 0))
        self._files_box_in = box_in

    def _build_options(self, parent):
        outer, body, _h = self._card(parent, "2  ·  Options")
        outer.grid(row=1, column=0, sticky="ew")

        ttk.Label(body, text="Remote directory on each PC", style="Card.TLabel").pack(anchor="w")
        ttk.Entry(body, textvariable=self.remote_dir_var).pack(fill="x", pady=(3, 10))

        ttk.Checkbutton(body, text="Replace the old if already exist", variable=self.replace_var,
                        style="Card.TCheckbutton", command=self._on_replace_toggle).pack(anchor="w")
        ttk.Label(body, text="Turn off to leave files that are already on the PC untouched.",
                  style="Hint.TLabel", wraplength=420).pack(anchor="w", padx=(24, 0), pady=(0, 8))

        self.force_check = ttk.Checkbutton(body, text="Force re-upload (even if same size)",
                                           variable=self.force_var, style="Card.TCheckbutton")
        self.force_check.pack(anchor="w")
        ttk.Label(body, text="Normally a file with the same size is skipped as already up to date.",
                  style="Hint.TLabel", wraplength=420).pack(anchor="w", padx=(24, 0))

    def _build_deploy(self, parent):
        outer, body, _h = self._card(parent)
        outer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        body.grid_columnconfigure(0, weight=1)

        info = ttk.Frame(body, style="Card.TFrame")
        info.grid(row=0, column=0, sticky="ew", padx=(0, 16))
        self.summary_label = ttk.Label(info, text="", style="CardTitle.TLabel")
        self.summary_label.pack(anchor="w")
        self.status_label = ttk.Label(info, text="Idle", style="Hint.TLabel", wraplength=480)
        self.status_label.pack(anchor="w", pady=(2, 0))
        self.progress = ttk.Progressbar(info, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", pady=(8, 0))

        controls = ttk.Frame(body, style="Card.TFrame")
        controls.grid(row=0, column=1, sticky="e")
        ttk.Label(controls, text="PCs at once", style="Card.TLabel").pack(side="left")
        spin = ttk.Spinbox(controls, from_=1, to=MAX_WORKERS, width=4, justify="center",
                           textvariable=self.workers_var)
        spin.pack(side="left", padx=(6, 16))
        spin.bind("<FocusOut>", lambda _e: self.workers_var.set(str(self._workers_value())))
        self.deploy_btn = ttk.Button(controls, text="Deploy", style="Success.TButton",
                                     width=12, command=self.deploy)
        self.deploy_btn.pack(side="left")
        self.cancel_btn = ttk.Button(controls, text="Stop", style="Danger.TButton",
                                     width=9, command=self.cancel_deploy, state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))
        T.add_tooltip(self.deploy_btn, "Send the files to the ticked store PCs")
        T.add_tooltip(self.cancel_btn, "Stop the deployment that is running")

    def _build_stores(self, parent):
        outer, body, _h = self._card(parent, "3  ·  Store PCs")
        outer.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        parent.grid_rowconfigure(0, weight=3, minsize=230)

        top = ttk.Frame(body, style="Card.TFrame")
        top.pack(fill="x")
        ttk.Label(top, text="Search", style="Card.TLabel").pack(side="left")
        ttk.Entry(top, textvariable=self.search_var).pack(side="left", fill="x", expand=True,
                                                          padx=(8, 0))
        self.search_var.trace_add("write", lambda *_: self._schedule_filter())

        btns = ttk.Frame(body, style="Card.TFrame")
        btns.pack(fill="x", pady=(8, 6))
        for text, cmd, tip in (
                ("Select All", self.select_shown, "Tick every store currently shown in the list"),
                ("Deselect All", self.clear_selection, "Untick all stores"),
                ("Select Failed", self.select_failed, "Tick the stores that failed in the last run"),
                ("Refresh", self.reload_stores, "Read stores.txt again"),
                ("Edit List", self.edit_stores, "Add or change store PCs")):
            b = ttk.Button(btns, text=text, style="Small.TButton", command=cmd)
            b.pack(side="left", padx=(0, 6))
            T.add_tooltip(b, tip)

        box = tk.Frame(body, bg=T.BORDER)
        box.pack(fill="both", expand=True)
        box_in = tk.Frame(box, bg=T.CARD)
        box_in.pack(fill="both", expand=True, padx=1, pady=1)
        self.tree = ttk.Treeview(box_in, show="tree", selectmode="none", height=5)
        sb = ttk.Scrollbar(box_in, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("group", background=T.GROUP_BG, font=T.FONT_BOLD)
        self.tree.tag_configure("checked", background=T.ACCENT_SOFT)
        self.tree.tag_configure("empty", foreground=T.MUTED)
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<space>", lambda _e: self._toggle_focused())

        self.store_count_label = ttk.Label(body, text="", style="Hint.TLabel")
        self.store_count_label.pack(anchor="w", pady=(6, 0))

    def _build_log(self, parent):
        outer, body, header = self._card(parent, "Activity log")
        outer.grid(row=1, column=0, sticky="nsew")
        parent.grid_rowconfigure(1, weight=2, minsize=110)
        log_btn = ttk.Button(header, text="Open Log", style="Small.TButton",
                             command=self.open_log_file)
        log_btn.pack(side="right")
        T.add_tooltip(log_btn, "Open the full log file")
        copy_btn = ttk.Button(header, text="Copy Failed", style="Small.TButton",
                              command=self.copy_failed)
        copy_btn.pack(side="right", padx=(0, 6))
        T.add_tooltip(copy_btn, "Copy the IPs of the stores that failed in the last run")

        box = tk.Frame(body, bg=T.BORDER)
        box.pack(fill="both", expand=True)
        box_in = tk.Frame(box, bg="#fafbfd")
        box_in.pack(fill="both", expand=True, padx=1, pady=1)
        self.log_text = tk.Text(box_in, height=4, font=T.FONT_MONO, wrap="word", state="disabled",
                                bg="#fafbfd", fg=T.TEXT, relief="flat", bd=0, highlightthickness=0,
                                padx=8, pady=6)
        sb = ttk.Scrollbar(box_in, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.log_text.tag_configure("ok", foreground=T.SUCCESS)
        self.log_text.tag_configure("failed", foreground=T.DANGER)
        self.log_text.tag_configure("cancelled", foreground=T.WARNING)
        self.log_text.tag_configure("muted", foreground=T.MUTED)
        self.log_text.tag_configure("heading", foreground=T.ACCENT_DARK, font=("Consolas", 9, "bold"))

    # ------------------------------------------------------------- files
    def choose_files(self):
        paths = filedialog.askopenfilenames(parent=self.root, title="Choose files to deploy")
        same_name = []
        for p in paths:
            name = os.path.basename(p)
            if any(f["path"] == p for f in self.files):
                continue
            if any(f["name"].lower() == name.lower() for f in self.files):
                same_name.append(name)
                continue
            self.files.append({"path": p, "name": name})
        if same_name:
            messagebox.showwarning(
                "Same file name",
                "These files were not added because a file with the same name is already in "
                "the list (they would overwrite each other on the PC):\n\n" + "\n".join(same_name))
        self._refresh_files()

    def remove_selected(self):
        for idx in reversed(list(self.files_listbox.curselection())):
            del self.files[idx]
        self._refresh_files()

    def clear_files(self):
        self.files.clear()
        self._refresh_files()

    def _refresh_files(self):
        self.files_listbox.delete(0, tk.END)
        total = 0
        for f in self.files:
            try:
                size = os.path.getsize(f["path"])
            except OSError:
                size = None
            if size is not None:
                total += size
            self.files_listbox.insert(tk.END, f"{f['name']}    ({fmt_size(size) if size is not None else 'missing'})")
        if self.files:
            self.files_empty.place_forget()
            self.files_info.config(text=f"{len(self.files)} file(s) · {fmt_size(total)}")
        else:
            self.files_empty.place(relx=0.5, rely=0.5, anchor="center")
            self.files_info.config(text="")
        self._update_summary()

    def _on_replace_toggle(self):
        self.force_check.state(["!disabled"] if self.replace_var.get() else ["disabled"])

    def _workers_value(self):
        try:
            n = int(self.workers_var.get())
        except (TypeError, ValueError):
            n = DEFAULT_WORKERS
        return max(1, min(MAX_WORKERS, n))

    # ------------------------------------------------------- store tree
    @staticmethod
    def _store_text(s):
        bits = [s["name"]]
        if s["code"]:
            bits.append(f"[{s['code']}]")
        bits.append(f"({s['ip']})")
        text = " ".join(bits)
        return f"{text} · {s['pos']}" if s["pos"] else text

    def _schedule_filter(self):
        if self._filter_job is not None:
            self.root.after_cancel(self._filter_job)
        self._filter_job = self.root.after(200, self._rebuild_tree)

    def _rebuild_tree(self):
        self._filter_job = None
        query = self.search_var.get().strip().lower()
        was_open = {self.group_names.get(g): self.tree.item(g, "open")
                    for g in self.tree.get_children() if g in self.group_names}
        self.tree.delete(*self.tree.get_children())
        self.row_to_idx.clear()
        self.group_children.clear()
        self.group_names.clear()

        groups = {}
        for idx, s in enumerate(self.stores):
            hay = " ".join((s["name"], s["code"], s["ip"], s["pos"], s["dc"])).lower()
            if query and query not in hay:
                continue
            groups.setdefault(s["dc"], []).append(idx)

        if not groups:
            msg = ("No store matches your search" if query
                   else "No stores yet — click “Edit stores” to add some")
            self.tree.insert("", "end", iid="empty", text="   " + msg, tags=("empty",))
        for k, dc in enumerate(sorted(groups)):
            gid = f"g{k}"
            self.group_names[gid] = dc
            self.group_children[gid] = groups[dc]
            self.tree.insert("", "end", iid=gid, text="", open=was_open.get(dc, True))
            for idx in groups[dc]:
                iid = f"s{idx}"
                self.row_to_idx[iid] = idx
                self.tree.insert(gid, "end", iid=iid, text="")
        self._refresh_rows()

    def _update_store_row(self, iid):
        idx = self.row_to_idx[iid]
        on = idx in self.selected
        self.tree.item(iid, text=f"{'☑' if on else '☐'}  {self._store_text(self.stores[idx])}",
                       tags=("checked",) if on else ())

    def _update_group_row(self, gid):
        idxs = self.group_children[gid]
        n = sum(1 for i in idxs if i in self.selected)
        box = "☑" if n and n == len(idxs) else ("▣" if n else "☐")
        self.tree.item(gid, text=f"{box}  {self.group_names[gid]}   ({n}/{len(idxs)} selected)",
                       tags=("group",))

    def _refresh_rows(self):
        for gid in self.group_children:
            self._update_group_row(gid)
        for iid in self.row_to_idx:
            self._update_store_row(iid)
        self._after_selection_change()

    def _after_selection_change(self):
        shown = len(self.row_to_idx)
        text = f"{len(self.selected)} selected  ·  {len(self.stores)} store(s) in the list"
        if shown != len(self.stores):
            text += f"  ·  {shown} shown"
        self.store_count_label.config(text=text)
        self._update_summary()

    def _on_tree_click(self, event):
        if self.tree.identify_region(event.x, event.y) not in ("tree", "cell"):
            return
        if "indicator" in self.tree.identify_element(event.x, event.y):
            return                      # the little arrow expands/collapses a group
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.focus(iid)
            self._toggle(iid)
        return "break"

    def _toggle_focused(self):
        iid = self.tree.focus()
        if iid:
            self._toggle(iid)
        return "break"

    def _toggle(self, iid):
        if iid in self.group_children:
            idxs = self.group_children[iid]
            if all(i in self.selected for i in idxs):
                self.selected.difference_update(idxs)
            else:
                self.selected.update(idxs)
            for child in self.tree.get_children(iid):
                self._update_store_row(child)
            self._update_group_row(iid)
        elif iid in self.row_to_idx:
            idx = self.row_to_idx[iid]
            self.selected.symmetric_difference_update({idx})
            self._update_store_row(iid)
            self._update_group_row(self.tree.parent(iid))
        else:
            return
        self._after_selection_change()

    def select_shown(self):
        self.selected.update(self.row_to_idx.values())
        self._refresh_rows()

    def clear_selection(self):
        self.selected.clear()
        self._refresh_rows()

    def _select_by_keys(self, keys):
        wanted = set(keys)
        self.selected = {i for i, s in enumerate(self.stores) if store_key(s) in wanted}
        self._refresh_rows()
        return len(self.selected)

    def select_failed(self):
        if not self.failed_keys:
            messagebox.showinfo("No failed stores",
                                "There are no failed stores from the last run in this session.")
            return
        n = self._select_by_keys(self.failed_keys)
        self._log(f"Ticked {n} store(s) that failed in the last run.", "muted")

    def copy_failed(self):
        if not self.failed_keys:
            messagebox.showinfo("No failed stores",
                                "There are no failed stores from the last run in this session.")
            return
        ordered = sorted(self.failed_keys, key=lambda k: (k[1], k[0]))   # by store code, then IP
        ips = list(dict.fromkeys(ip for ip, _code, _pos in ordered))     # no duplicates
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(ips))
        self.root.update()                                               # keeps it after the app closes
        self._log(f"Copied {len(ips)} failed IP address(es) to the clipboard.", "muted")
        messagebox.showinfo("Copied", f"Copied {len(ips)} IP address(es) to the clipboard,\n"
                                      f"one per line.")
        
    def reload_stores(self):
        keys = [store_key(self.stores[i]) for i in self.selected if i < len(self.stores)]
        self.stores, self.store_warnings = load_stores()
        self.selected.clear()
        self._rebuild_tree()
        self._select_by_keys(keys)
        self._log(f"Reloaded stores.txt: {len(self.stores)} store(s).", "muted")
        for w in self.store_warnings:
            self._log(f"⚠ {w}", "cancelled")

    def edit_stores(self):
        if self._editor is not None and self._editor.winfo_exists():
            self._editor.lift()
            self._editor.focus_force()
            return
        self._editor = open_stores_editor(self.root, on_save=self.reload_stores)

    def open_log_file(self):
        if not os.path.exists(LOG_FILE):
            messagebox.showinfo("No log file", "Nothing has been logged yet.")
            return
        try:
            os.startfile(LOG_FILE)
        except (AttributeError, OSError):
            messagebox.showinfo("Log file", f"The log file is here:\n\n{LOG_FILE}")

    # --------------------------------------------------------------- log
    def _append_panel(self, lines):
        chunks = []
        for text, tag in lines:
            chunks.extend((text + "\n", tag or ""))
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, *chunks)
        count = int(self.log_text.index("end-1c").split(".")[0]) - 1
        if count > LOG_PANEL_MAX_LINES:
            self.log_text.delete("1.0", f"{count - LOG_PANEL_MAX_LINES + 1}.0")
        self.log_text.config(state="disabled")
        self.log_text.see(tk.END)

    def _log_many(self, lines):
        write_log_file([(t, level_of(tag)) for t, tag in lines])
        self._append_panel(lines)

    def _log(self, text, tag=None):
        self._log_many([(text, tag)])

    def _update_summary(self):
        if self.cancel_event is not None:
            return
        nf, ns = len(self.files), len(self.selected)
        if nf and ns:
            self.summary_label.config(text=f"{nf} file(s)  →  {ns} store PC(s)")
            self.status_label.config(text="Ready to deploy")
        else:
            self.summary_label.config(text="Add files and tick store PCs to begin")
            self.status_label.config(text="Idle")

    # ------------------------------------------------------------ deploy
    def _set_running(self, running):
        self.deploy_btn.config(state="disabled" if running else "normal",
                               text="Deploying…" if running else "Deploy")
        self.cancel_btn.config(state="normal" if running else "disabled", text="Stop")

    def deploy(self):
        if self.cancel_event is not None:
            return
        stores = [s for i, s in enumerate(self.stores) if i in self.selected]
        if not self.files:
            messagebox.showwarning("No files", "Add at least one file to deploy.")
            return
        if not stores:
            messagebox.showwarning("No store PCs", "Tick at least one store PC.")
            return
        missing = [f["path"] for f in self.files if not os.path.exists(f["path"])]
        if missing:
            messagebox.showwarning("File missing",
                                   "These files are no longer on this computer:\n\n" + "\n".join(missing))
            return

        remote_dir = self.remote_dir_var.get().strip() or DEFAULT_REMOTE_DIR
        replace = self.replace_var.get()
        force = self.force_var.get() and replace
        workers = self._workers_value()
        self.workers_var.set(str(workers))

        lines = [f"Upload {len(self.files)} file(s) to {remote_dir}",
                 f"on {len(stores)} store PC(s).", "",
                 "Files already on a PC: " + ("replaced" if replace else "left untouched")]
        if replace:
            lines.append("Same-size files: " + ("re-uploaded (Force is on)" if force
                                                else "skipped as up to date"))
        lines += ["", "Proceed?"]
        if not messagebox.askyesno("Confirm Deployment", "\n".join(lines)):
            return

        files = [dict(f) for f in self.files]
        self.results, self.counts = [], {}
        self.run_total = len(stores)
        self.step_text = ""
        self.cancelling = False
        self.run_started = time.monotonic()

        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state="disabled")
        header = [("", None), (RULE, None),
                  (f"RUN STARTED {datetime.now():%Y-%m-%d %H:%M:%S}  ·  {len(stores)} store(s)", "heading"),
                  (f"Folder: {remote_dir}", None),
                  (f"Replace: {'on' if replace else 'off'}  ·  Force: {'on' if force else 'off'}"
                   f"  ·  Workers: {workers}", None)]
        for f in files:
            try:
                size = f"  ({fmt_size(os.path.getsize(f['path']))})"
            except OSError:
                size = ""
            header.append((f"  • {f['name']}{size}", None))
        header.append((RULE, None))
        self._log_many(header)

        self._set_running(True)
        self.progress.config(maximum=len(stores), value=0)
        self.summary_label.config(text=f"Deploying to {len(stores)} store PC(s)…")
        self.cancel_event = start_deployment(stores, files, remote_dir, replace, force,
                                             workers, self.log_queue)
        self.root.after(100, self._poll)

    def cancel_deploy(self):
        if self.cancel_event is None or self.cancel_event.is_set():
            return
        if not messagebox.askyesno(
                "Stop Deployment?",
                "PCs already in progress will finish their current file; PCs that haven't "
                "started will be skipped.\n\nStop the deployment?"):
            return
        self.cancel_event.set()
        self.cancelling = True
        self.cancel_btn.config(state="disabled", text="Stopping…")
        self._log("--- STOP REQUESTED ---", "failed")

    def _poll(self):
        entries, progress_add, finished, more = [], 0, False, True
        try:
            for _ in range(POLL_BATCH):
                kind, payload, tag = self.log_queue.get_nowait()
                if kind == "log":
                    entries.append((payload, tag, True))
                elif kind == "detail":
                    entries.append((payload, None, False))
                elif kind == "status":
                    self.step_text = payload
                elif kind == "progress":
                    progress_add += payload
                elif kind == "result":
                    self.results.append(payload)
                    self.counts[payload["status"]] = self.counts.get(payload["status"], 0) + 1
                elif kind == "done":
                    finished = True
                    break
        except queue.Empty:
            more = False
        if finished:
            more = False

        if entries:
            write_log_file([(t, level_of(tag)) for t, tag, _s in entries])
            shown = [(t, tag) for t, tag, show in entries if show]
            if shown:
                self._append_panel(shown)
        if progress_add:
            self.progress["value"] = self.progress["value"] + progress_add
        if finished:
            self._finish_run()
            return
        self._update_status()
        self.root.after(20 if more else 100, self._poll)

    def _counts_text(self):
        parts = [f"{ICON[k]} {self.counts[k]} {LABEL[k]}" for k in ("ok", "failed", "cancelled")
                 if self.counts.get(k)]
        return "  ·  ".join(parts) if parts else "No stores processed"

    def _update_status(self):
        parts = []
        if self.cancelling:
            parts.append("Cancelling — waiting for in-progress PCs to stop…")
        done = sum(self.counts.values())
        parts.append(f"Done {done}/{self.run_total}")
        if done:
            parts.append(self._counts_text())
        if self.run_total <= 3 and self.step_text and not self.cancelling:
            parts.append(self.step_text)
        self.status_label.config(text="  ·  ".join(parts))

    def _finish_run(self):
        cancelled = self.cancel_event is not None and self.cancel_event.is_set()
        elapsed = time.monotonic() - self.run_started if self.run_started else 0
        failed = [r for r in self.results if r["status"] == "failed"]
        self.failed_keys = [(r["ip"], r["code"], r["pos"]) for r in failed]

        lines = [("", None), (RULE, None),
                 (f"RUN {'STOPPED' if cancelled else 'FINISHED'} in {fmt_elapsed(elapsed)}", "heading"),
                 (self._counts_text(), None)]
        if failed:
            by_reason = {}
            for r in failed:
                by_reason.setdefault(r["reason"], []).append(r["store"])
            lines.append(("Problems by reason:", None))
            for reason, names in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
                lines.append((f"  ✗ {len(names)} × {reason}", "failed"))
                lines.extend((f"      {n}", None) for n in names[:10])
                if len(names) > 10:
                    lines.append((f"      … and {len(names) - 10} more", None))
                lines.append(("Click “Select Failed” to tick these stores, then Deploy again.", None))
        lines.append((RULE, None))
        self._log_many(lines)

        counts_text = self._counts_text()
        self.cancel_event = None
        self.cancelling = False
        self._set_running(False)
        self.summary_label.config(text="Stopped" if cancelled else "Finished")
        self.status_label.config(text=counts_text)
        title = "Deployment stopped" if cancelled else "Deployment finished"
        msg = f"{counts_text}\n\nSee the Activity log for the reason behind each failure."
        (messagebox.showwarning if failed else messagebox.showinfo)(title, msg)