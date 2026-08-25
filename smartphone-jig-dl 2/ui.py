import json
import os
import queue
import re
import sys
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import ctypes
from ctypes import wintypes

# Garante que o Tkinter e a API do Windows usem os pixels reais do monitor,
# corrigindo desalinhamentos se o Windows estiver com zoom de 125%, 150%, etc.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from pywinauto import Desktop

class SetupApp(tk.Tk):
    STEP_TYPES = ["None", "Click At Coordinates", "Keyboard Typing", "Press Key"]
    KEY_OPTIONS = ["Enter", "Tab", "Spacebar", "Backspace"]
    KEY_VALUE_MAP = {"Enter": "enter", "Tab": "tab", "Spacebar": "space", "Backspace": "backspace"}
    KEY_LABEL_MAP = {v: k for k, v in KEY_VALUE_MAP.items()}
    STEP_TYPE_TO_LABEL = {"none": "None", "click": "Click At Coordinates", "type_text": "Keyboard Typing", "key_press": "Press Key"}
    STEP_LABEL_TO_TYPE = {v: k for k, v in STEP_TYPE_TO_LABEL.items()}

    GRID_LINE = "#b0b0b0"
    HEADER_BG = "#e8e8e8"
    ROW_BG = "#ffffff"
    ROW_BG_ALT = "#f5f8fc"
    HEADER_FONT = ("Segoe UI", 9, "bold")
    CELL_FONT = ("Segoe UI", 9)
    DANGER_BG = "#e57373"

    STOP_ACTIVE_BG = "#e57373"
    STOP_INACTIVE_BG = "#fbe4e4"
    STATUS_ON_BG = "#00e5ff"
    STATUS_OFF_BG = "#cfd8dc"

    def __init__(self, config_filename="config.json"):
        super().__init__()
        self.title("Downloader App - Configuration Manager")
        self.geometry("660x700")
        self.minsize(600, 520)
        self.config_filename = config_filename

        self._int_vcmd = (self.register(self._validate_integer_input), "%P")

        self.settings_entries = {}
        self.slot_entries = {}
        self.server_process = None
        self._locked = False
        self._stopping = False
        self._stopping_deadline = None
        self._confirmed_running = False
        self._console_queue = queue.Queue()
        self._console_reader_thread = None
        self._dirty = False
        self._last_saved_payload = None

        self._init_ui()
        self.load_config()

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.after(150, self._poll_console_queue)
        self.after(300, self._poll_dirty_state)

    def _init_ui(self):
        # --- NOTEBOOK ---
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=4)

        self.tab_settings = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_settings, text="Server Settings")
        self._setup_settings_tab()

        self.tab_auto_script = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_auto_script, text="Auto Script")
        self._setup_auto_script_tab()

        self.tab_log_file = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_log_file, text="Log File")
        self._setup_log_file_tab()

        # --- FOOTER ---
        footer = ttk.Frame(self)
        footer.pack(fill="x", side="bottom", padx=8, pady=6)

        self.btn_start = tk.Button(
            footer, text="Start", font=("Segoe UI", 11, "bold"), width=8, bd=2,
            relief="raised", highlightthickness=0, command=self._on_start_clicked,
        )
        self.btn_start.pack(side="left")

        self.btn_stop = tk.Button(
            footer, text="Stop", font=("Segoe UI", 11, "bold"), width=8, bd=2,
            relief="raised", highlightthickness=0, command=self._on_stop_clicked,
        )
        self.btn_stop.pack(side="left", padx=(1, 0))

        self.status_label = tk.Label(
            footer, text="OFF", font=("Segoe UI", 11, "bold"), width=16, bd=2,
            relief="sunken", highlightthickness=0, pady=4,
        )
        self.status_label.pack(side="left", padx=(1, 0))

        self.btn_save = ttk.Button(footer, text="Save", command=self.save_config)
        self.btn_save.pack(side="right")

        self.btn_reload = ttk.Button(footer, text="Reload", command=self.load_config)
        self.btn_reload.pack(side="right", padx=(0, 1))

    # --- SHARED HELPERS ---
    def _validate_integer_input(self, proposed):
        if proposed in ("", "-"):
            return True
        return bool(re.fullmatch(r"-?\d+", proposed))

    def _safe_int(self, value, default=0):
        value = (value or "").strip()
        if value in ("", "-"):
            return default
        try:
            return int(value)
        except ValueError:
            return default

    def _make_scrollable(self, parent):
        canvas = tk.Canvas(parent, highlightthickness=0, bg="#ffffff")
        vscroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg="#ffffff")

        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfigure(inner_id, width=event.width)

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=vscroll.set)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_wheel(_):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_wheel(_):
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)

        canvas.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y")

        return canvas, inner

    # --- SERVER CONTROL ---
    def _resolve_main_process_path(self):
        filename = self.settings_entries["MAIN_PROCESS_FILE"].get().strip() or "main.py"

        if os.path.isabs(filename):
            return filename

        base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
            else os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, filename)

    def _kill_process_tree(self, proc):
        """Kills proc and every descendant it spawned.

        proc.terminate() alone only kills that one PID. A PyInstaller
        --onefile EXE on Windows runs as a launcher that unpacks itself to a
        temp dir and spawns a child process to do the real work; killing
        only the launcher orphans that child, which keeps running (and keeps
        the port bound) invisibly to us, showing up in Task Manager forever.
        `taskkill /T` walks and kills the whole tree instead.
        """
        if proc is None:
            return
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass

    def _on_start_clicked(self):
        if self.server_process is not None:
            return

        target_path = self._resolve_main_process_path()

        if not os.path.isfile(target_path):
            messagebox.showerror(
                "Error",
                f"Main process file not found:\n{target_path}\n\n"
                "Check 'Main Process File' in Server Settings.",
            )
            return

        cmd = [sys.executable, "-u", target_path] if target_path.lower().endswith(".py") else [target_path]

        try:
            self._confirmed_running = False
            self.server_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=os.path.dirname(target_path) or None,
            )
            self._append_console_line(f"--- Started {os.path.basename(target_path)} (PID {self.server_process.pid}) ---")
            self._start_output_reader_thread()
            self._locked = True
            self._apply_states()
        except Exception as e:
            self.server_process = None
            messagebox.showerror("Error", f"Failed to start {os.path.basename(target_path)}:\n{str(e)}")
            self._update_run_controls()

    def _on_stop_clicked(self):
        if self.server_process is None or self._stopping:
            return

        # Don't flip to OFF / unlock right away: on Windows, terminating a
        # process doesn't guarantee its listening socket is released
        # immediately. If the user hits Start again too fast, the new
        # process can fail to bind with "only one usage of each socket
        # address is normally permitted". Stay locked (status shows
        # STOPPING...) until _poll_console_queue confirms the process has
        # actually exited.
        self._append_console_line(f"--- Stopping process (PID {self.server_process.pid}) ---")
        self._kill_process_tree(self.server_process)
        self._stopping = True
        self._stopping_deadline = time.monotonic() + 10.0
        self._confirmed_running = False
        self._update_run_controls()

    def _start_output_reader_thread(self):
        proc = self.server_process

        def _reader():
            try:
                for line in iter(proc.stdout.readline, ""):
                    if not line:
                        break
                    self._console_queue.put(line.rstrip("\n"))
            except Exception:
                pass
            finally:
                if proc.stdout:
                    proc.stdout.close()

        self._console_reader_thread = threading.Thread(target=_reader, daemon=True)
        self._console_reader_thread.start()

    def _append_console_line(self, text):
        self.console_output.configure(state="normal")
        self.console_output.insert("end", text + "\n")
        self.console_output.see("end")
        self.console_output.configure(state="disabled")

    def _poll_console_queue(self):
        try:
            while True:
                line = self._console_queue.get_nowait()
                self._append_console_line(line)

                # This is uvicorn's own startup line (e.g. "Uvicorn running on
                # http://127.0.0.1:8000 (Press CTRL+C to quit)"). Host/port
                # are dynamic (from config), so match on the fixed part only.
                # Only once this shows up do we consider the server truly ON
                # -- a spawned process isn't proof it actually bound the port.
                if not self._confirmed_running and "uvicorn running on" in line.lower():
                    self._confirmed_running = True
                    self._update_run_controls()
        except queue.Empty:
            pass

        # Detect the process dying on its own (crash, closed manually, etc.)
        # so status doesn't stay stuck on ON. Also used to confirm a
        # user-requested stop has actually finished before unlocking the UI
        # (see _on_stop_clicked) so a fast Stop->Start doesn't race the OS
        # releasing the port.
        if self.server_process is not None:
            exited = self.server_process.poll() is not None
            timed_out = (
                self._stopping and self._stopping_deadline is not None
                and time.monotonic() > self._stopping_deadline
            )

            if exited:
                self._append_console_line(f"--- Process exited (code {self.server_process.returncode}) ---")
            elif timed_out:
                self._append_console_line(
                    "--- WARNING: process did not exit within 10s; resetting status to OFF anyway ---"
                )

            if exited or timed_out:
                self.server_process = None
                self._stopping = False
                self._stopping_deadline = None
                self._confirmed_running = False
                self._locked = False
                self._apply_states()

        self.after(150, self._poll_console_queue)

    # --- DIRTY / SAVE STATE ---
    def _poll_dirty_state(self):
        try:
            current = self._collect_settings_payload()
            dirty = current != self._last_saved_payload
        except Exception:
            # Mid-edit invalid input (e.g. PORT momentarily empty) still
            # counts as "not matching what's saved on disk".
            dirty = True

        if dirty != self._dirty:
            self._dirty = dirty
            self._update_run_controls()

        self.after(300, self._poll_dirty_state)

    def _update_run_controls(self):
        """Drives the Start/Stop pushbutton pair and the ON/OFF status light
        from the current run state, plus the Save button from dirty state.

        Start/Stop behave like a two-position control-panel switch: whichever
        one reflects the CURRENT status appears pressed (sunken) and is
        disabled (nothing to do by pressing it again); the other is
        unpressed (raised) and, if applicable, enabled. Only Stop carries
        color (salmon, saturated when pressed / pale when not) -- Start
        stays neutral and communicates its state through relief alone.
        """
        running = self.server_process is not None
        can_edit = not self._locked

        self.btn_save.configure(state="normal" if (self._dirty and can_edit) else "disabled")

        if self._stopping:
            start_pressed, start_enabled = False, False
            stop_pressed, stop_enabled = True, False
            status_text, status_bg, status_fg = "STOPPING...", self.STATUS_OFF_BG, "black"
        elif running and self._confirmed_running:
            start_pressed, start_enabled = True, False
            stop_pressed, stop_enabled = False, True
            status_text, status_bg, status_fg = "ON", self.STATUS_ON_BG, "black"
        elif running:  # process spawned, waiting for uvicorn's own confirmation
            start_pressed, start_enabled = True, False
            stop_pressed, stop_enabled = False, True
            status_text, status_bg, status_fg = "STARTING...", self.STATUS_OFF_BG, "black"
        else:  # fully stopped
            start_pressed, start_enabled = False, (not self._dirty) and can_edit
            stop_pressed, stop_enabled = True, False
            status_text, status_bg, status_fg = "OFF", self.STATUS_OFF_BG, "black"

        self.btn_start.configure(
            relief="sunken" if start_pressed else "raised",
            state="normal" if start_enabled else "disabled",
        )
        self.btn_stop.configure(
            bg=self.STOP_ACTIVE_BG if stop_pressed else self.STOP_INACTIVE_BG,
            relief="sunken" if stop_pressed else "raised",
            state="normal" if stop_enabled else "disabled",
        )
        self.status_label.configure(text=status_text, bg=status_bg, fg=status_fg)

    def _apply_states(self):
        """Recomputes the enabled/disabled state of every widget based on
        whether the server is running (locked) and each Slot's/Action's own
        enabled checkbox."""
        global_state = "disabled" if self._locked else "normal"

        for entry in self.settings_entries.values():
            if isinstance(entry, (tk.Entry, ttk.Entry)):
                entry.configure(state=global_state)
        for entry in self.range_entries.values():
            entry.configure(state=global_state)
        for row in self.extract_field_rows:
            for entry in row["widgets"].values():
                entry.configure(state=global_state)
            row["delete_btn"].configure(state=global_state)

        self.btn_window_picker.configure(state=global_state)
        self.btn_log_picker.configure(state=global_state)
        self.btn_reload.configure(state=global_state)
        self.btn_add_slot.configure(state=global_state)
        self.btn_add_extract_field.configure(state=global_state)

        for slot in self.slot_entries.values():
            # Slot-level enable checkbox and delete button stay usable
            # (unless the server is locked) so the user can always toggle
            # or remove a slot.
            slot["enabled_check"].configure(state=global_state)
            slot["delete_btn"].configure(state=global_state)

            slot_active = (not self._locked) and slot["enabled_var"].get()
            slot_state = "normal" if slot_active else "disabled"

            slot["add_action_btn"].configure(state=slot_state)

            for action in slot["actions"]:
                action["enabled_check"].configure(state=slot_state)
                action["delete_btn"].configure(state=slot_state)

                action_active = slot_active and action["enabled_var"].get()
                a_state = "normal" if action_active else "disabled"
                a_combo_state = "readonly" if action_active else "disabled"

                action["combo"].configure(state=a_combo_state)
                for w in action["widgets"].values():
                    if isinstance(w, ttk.Combobox):
                        w.configure(state=a_combo_state)
                    elif isinstance(w, (tk.Button, ttk.Button)):
                        w.configure(state=a_state)
                    elif isinstance(w, (tk.Entry, ttk.Entry)):
                        w.configure(state=a_state)

        self._update_run_controls()

    def on_closing(self):
        if self.server_process is not None:
            self._kill_process_tree(self.server_process)
        self.destroy()

    # --- TAB 1: SERVER SETTINGS ---
    def _setup_settings_tab(self):
        container = ttk.Frame(self.tab_settings)
        container.pack(fill="both", expand=True, padx=0, pady=8)

        settings_table = tk.Frame(container, bg=self.GRID_LINE)
        settings_table.pack(fill="x")

        def _add_settings_row(row, label_text, build_cell):
            tk.Label(
                settings_table, text=label_text, font=self.HEADER_FONT, bg=self.HEADER_BG,
                anchor="w",
            ).grid(row=row, column=0, padx=(0, 1), pady=(0, 1), ipady=4, ipadx=6, sticky="nsew")

            cell = tk.Frame(settings_table, bg=self.ROW_BG)
            cell.grid(row=row, column=1, padx=(0, 1), pady=(0, 1), sticky="nsew")
            build_cell(cell)

        def _build_host(cell):
            self.settings_entries["SERVER_HOST_IP"] = tk.Entry(cell, width=30)
            self.settings_entries["SERVER_HOST_IP"].pack(side="left", padx=4, pady=3)

        def _build_port(cell):
            self.settings_entries["SERVER_PORT"] = tk.Entry(cell, width=30)
            self.settings_entries["SERVER_PORT"].pack(side="left", padx=4, pady=3)

        def _build_window(cell):
            self.settings_entries["TARGET_WINDOW_TITLE"] = tk.Entry(cell, width=22)
            self.settings_entries["TARGET_WINDOW_TITLE"].pack(side="left", padx=(4, 6), pady=3)
            self.btn_window_picker = ttk.Button(
                cell, text="🪟 Pick Window", command=self._start_window_picker,
            )
            self.btn_window_picker.pack(side="left")

        def _build_main_process(cell):
            self.settings_entries["MAIN_PROCESS_FILE"] = tk.Entry(cell, width=30)
            self.settings_entries["MAIN_PROCESS_FILE"].pack(side="left", padx=4, pady=3)

        _add_settings_row(0, "SERVER_HOST_IP", _build_host)
        _add_settings_row(1, "SERVER_PORT", _build_port)
        _add_settings_row(2, "TARGET_WINDOW_TITLE", _build_window)
        _add_settings_row(3, "MAIN_PROCESS_FILE", _build_main_process)

        settings_table.grid_columnconfigure(0, weight=0)
        settings_table.grid_columnconfigure(1, weight=1)

        ttk.Label(
            container,
            text="MAIN_PROCESS_FILE is launched by Start/Stop (e.g. main.py while testing, main.exe once compiled).",
            font=("Segoe UI", 8), foreground="#555555",
        ).pack(fill="x", pady=(2, 8))

        ttk.Label(
            container, text="Process Output:", font=("Segoe UI", 9, "bold"),
        ).pack(fill="x", pady=(0, 2))

        self.console_output = scrolledtext.ScrolledText(
            container, height=4, width=50, state="disabled", wrap="word",
            bg="#1e1e1e", fg="#d4d4d4", insertbackground="#d4d4d4", font=("Consolas", 9),
        )
        self.console_output.pack(fill="both", expand=True)

    def _start_window_picker(self):
        self.btn_window_picker.configure(text="🔴 Hover & Click...", state="disabled")
        self._wait_for_release()

    def _wait_for_release(self):
        if ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000:
            self.after(50, self._wait_for_release)
        else:
            self.after(50, self._poll_window)

    def _poll_window(self):
        user32 = ctypes.windll.user32

        if user32.GetAsyncKeyState(0x1B) & 0x8000:
            self.btn_window_picker.configure(text="🪟 Pick Window", state="normal")
            return

        # Ao clicar, destrava a UI e salva no JSON silenciosamente
        if user32.GetAsyncKeyState(0x01) & 0x8000:
            self.btn_window_picker.configure(text="🪟 Pick Window", state="normal")
            self.save_config(silent=True)
            return

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        hwnd = user32.WindowFromPoint(pt)

        if hwnd:
            root_hwnd = user32.GetAncestor(hwnd, 2)
            length = user32.GetWindowTextLengthW(root_hwnd)

            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(root_hwnd, buff, length + 1)
                title = buff.value.strip()

                invalid_titles = ["Downloader App - Configuration Manager", "Program Manager", "Taskbar", "Windows Shell Experience Host"]

                if title and title not in invalid_titles:
                    entry = self.settings_entries["TARGET_WINDOW_TITLE"]
                    state_before = entry.cget("state")
                    entry.configure(state="normal")

                    entry.delete(0, tk.END)
                    entry.insert(0, title)

                    entry.configure(state=state_before)

        self.after(50, self._poll_window)

    def _start_capture_overlay(self, entry_x, entry_y, silent_save=True):
        target_title = self.settings_entries["TARGET_WINDOW_TITLE"].get().strip()

        if not target_title:
            messagebox.showerror("Erro", "Defina o TARGET_WINDOW_TITLE na aba 'Server Settings' primeiro.")
            return

        try:
            janela = Desktop(backend="uia").window(title=target_title)

            if not janela.exists():
                messagebox.showerror(
                    "Erro",
                    f"Janela '{target_title}' não foi encontrada.\nAbra o aplicativo alvo antes de capturar."
                )
                return

            if janela.is_minimized():
                janela.restore()

            janela.set_focus()

            rect = janela.rectangle()
            janela_left = rect.left
            janela_top = rect.top

        except Exception as e:
            messagebox.showerror("Erro de Conexão", f"Falha ao conectar com a janela '{target_title}':\n\n{str(e)}")
            return

        overlay = tk.Toplevel(self)
        overlay.attributes("-fullscreen", True)
        overlay.attributes("-alpha", 0.01)
        overlay.attributes("-topmost", True)
        overlay.config(cursor="crosshair")

        def on_mouse_click(event):
            pt = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))

            rel_x = pt.x - janela_left
            rel_y = pt.y - janela_top

            entry_x.delete(0, tk.END)
            entry_x.insert(0, str(rel_x))
            entry_y.delete(0, tk.END)
            entry_y.insert(0, str(rel_y))

            overlay.destroy()

            if silent_save:
                self.save_config(silent=True)  # Salva silenciosamente após pegar a coordenada

        def on_escape(event):
            overlay.destroy()

        overlay.bind("<Button-1>", on_mouse_click)
        overlay.bind("<Escape>", on_escape)

    # --- TAB 3: LOG FILE ---
    def _setup_log_file_tab(self):
        container = ttk.Frame(self.tab_log_file)
        container.pack(fill="both", expand=True, padx=0, pady=8)

        log_table = tk.Frame(container, bg=self.GRID_LINE)
        log_table.pack(fill="x")

        tk.Label(
            log_table, text="LOG_FILE_PATH", font=self.HEADER_FONT, bg=self.HEADER_BG,
            anchor="w",
        ).grid(row=0, column=0, padx=(0, 1), pady=(0, 1), ipady=4, ipadx=6, sticky="nsew")

        cell = tk.Frame(log_table, bg=self.ROW_BG)
        cell.grid(row=0, column=1, padx=(0, 1), pady=(0, 1), sticky="nsew")

        self.settings_entries["LOG_FILE_PATH"] = tk.Entry(cell, width=40)
        self.settings_entries["LOG_FILE_PATH"].pack(side="left", padx=4, pady=3, fill="x", expand=True)

        self.btn_log_picker = ttk.Button(
            cell, text="📁 Browse...", command=self._pick_log_file,
        )
        self.btn_log_picker.pack(side="left", padx=(6, 4), pady=3)

        log_table.grid_columnconfigure(0, weight=0)
        log_table.grid_columnconfigure(1, weight=1)

        ttk.Label(
            container,
            text="LOG_FILE_PATH is the location of the log file the application should read/monitor.",
            font=("Segoe UI", 8), foreground="#555555",
        ).pack(fill="x", pady=(2, 8))

        # --- DATA RANGE AND FIELD EXTRACTION ---
        ttk.Label(
            container,
            text=(
                "The range markers define one data context per barcode. Each field below is then "
                "extracted from that context. A field can optionally select a row, start after a "
                "reference word, and stop at a numeric or string position."
            ),
            wraplength=600, justify="left", font=("Segoe UI", 8), foreground="#555555",
        ).pack(fill="x", pady=(0, 6))

        self.range_entries = {}
        range_group = ttk.LabelFrame(container, text="1. Data Range Criteria")
        range_group.pack(fill="x", pady=(0, 8))
        range_table = tk.Frame(range_group, bg=self.GRID_LINE)
        range_table.pack(fill="x", padx=4, pady=4)

        for row, label, key in (
            (0, "Range Start Marker", "start_marker"),
            (1, "Range End Marker", "end_marker"),
        ):
            tk.Label(
                range_table, text=label, font=self.HEADER_FONT, bg=self.HEADER_BG, anchor="w",
            ).grid(row=row, column=0, padx=(0, 1), pady=(0, 1), ipady=4, ipadx=6, sticky="nsew")
            entry = tk.Entry(range_table)
            entry.grid(row=row, column=1, padx=(0, 1), pady=(0, 1), ipady=3, sticky="ew")
            self.range_entries[key] = entry
        range_table.grid_columnconfigure(1, weight=1)

        fields_group = ttk.LabelFrame(container, text="2. Data Fields to Extract")
        fields_group.pack(fill="x", pady=(0, 8))
        self.extract_fields_table = tk.Frame(fields_group, bg=self.GRID_LINE)
        self.extract_fields_table.pack(fill="x", padx=4, pady=(4, 2))
        self.EXTRACT_FIELD_HEADERS = [
            "Field Name", "String Marker (Optional)", "Start String (optional)",
            "Start", "Size", "End String (Optional)", "",
        ]
        for column, title in enumerate(self.EXTRACT_FIELD_HEADERS):
            tk.Label(
                self.extract_fields_table, text=title, font=self.HEADER_FONT,
                bg=self.HEADER_BG, anchor="center",
            ).grid(row=0, column=column, padx=(0, 1), pady=(0, 1), ipady=3, sticky="nsew")
        for column, weight in enumerate((1, 2, 2, 0, 0, 2, 0)):
            self.extract_fields_table.grid_columnconfigure(column, weight=weight)
        self.extract_field_rows = []

        fields_footer = ttk.Frame(fields_group)
        fields_footer.pack(fill="x", padx=4, pady=(0, 4))
        self.btn_add_extract_field = ttk.Button(
            fields_footer, text="+ Add Field", command=self._on_add_extract_field,
        )
        self.btn_add_extract_field.pack(side="left")

        # --- TRY OUT ---
        tryout_footer = ttk.Frame(container)
        tryout_footer.pack(fill="x", pady=(4, 4))

        self.btn_tryout = ttk.Button(
            tryout_footer, text="▶ Try Out Extraction", command=self._run_extraction_tryout,
        )
        self.btn_tryout.pack(side="left")

        ttk.Label(
            container, text="Extraction Result:", font=("Segoe UI", 9, "bold"),
        ).pack(fill="x", pady=(0, 2))

        tree_holder = tk.Frame(container)
        tree_holder.pack(fill="both", expand=True)

        self.extract_tree = ttk.Treeview(tree_holder, columns=("value",), show="tree headings")
        self.extract_tree.heading("#0", text="Key")
        self.extract_tree.heading("value", text="Value")
        self.extract_tree.column("#0", width=150, anchor="w")
        self.extract_tree.column("value", width=350, anchor="w")

        tree_vscroll = ttk.Scrollbar(tree_holder, orient="vertical", command=self.extract_tree.yview)
        self.extract_tree.configure(yscrollcommand=tree_vscroll.set)

        self.extract_tree.pack(side="left", fill="both", expand=True)
        tree_vscroll.pack(side="right", fill="y")

    def _on_add_extract_field(self, data=None):
        row_index = len(self.extract_field_rows) + 1
        table = self.extract_fields_table
        keys = ("name", "row_marker", "from_word", "pos_from", "pos_to", "end_word")
        widgets = {}
        for column, key in enumerate(keys):
            entry = tk.Entry(
                table, width=8 if key in ("pos_from", "pos_to") else 16,
                validate="key" if key in ("pos_from", "pos_to") else None,
                validatecommand=self._int_vcmd if key in ("pos_from", "pos_to") else None,
                font=self.CELL_FONT, bg=self.ROW_BG, relief="flat", bd=0, highlightthickness=0,
            )
            entry.grid(row=row_index, column=column, padx=(0, 1), pady=(0, 1), ipady=3, sticky="ew")
            widgets[key] = entry

        delete_btn = tk.Button(
            table, text="X", bg=self.DANGER_BG, fg="white", relief="flat", bd=0, highlightthickness=0,
            command=lambda: self._delete_extract_field(row),
        )
        delete_btn.grid(row=row_index, column=6, padx=(0, 1), pady=(0, 1), sticky="nsew")
        row = {"widgets": widgets, "delete_btn": delete_btn}
        self.extract_field_rows.append(row)
        if data:
            for key, entry in widgets.items():
                value = data.get("pos_from" if key == "pos_from" else "pos_to", 0) if key in ("pos_from", "pos_to") else data.get(key, "")
                if value not in (None, ""):
                    entry.insert(0, str(value))
        self._apply_states()
        return row

    def _delete_extract_field(self, row):
        row["delete_btn"].destroy()
        for entry in row["widgets"].values():
            entry.destroy()
        self.extract_field_rows.remove(row)
        for row_index, current in enumerate(self.extract_field_rows, start=1):
            for entry in current["widgets"].values():
                entry.grid_configure(row=row_index)
            current["delete_btn"].grid_configure(row=row_index)
        self._apply_states()

    def _pick_log_file(self):
        current = self.settings_entries["LOG_FILE_PATH"].get().strip()
        current_dir = os.path.dirname(current) if current else ""
        initial_dir = current_dir if current_dir and os.path.isdir(current_dir) else os.getcwd()

        selected = filedialog.askopenfilename(
            title="Select Log File",
            initialdir=initial_dir,
            filetypes=[("Log files", "*.log *.txt"), ("All files", "*.*")],
        )

        if selected:
            entry = self.settings_entries["LOG_FILE_PATH"]
            entry.delete(0, tk.END)
            entry.insert(0, selected)

    # --- LOG EXTRACTION ---
    def _require_extract_names(self):
        start_marker = self.range_entries["start_marker"].get().strip()
        end_marker = self.range_entries["end_marker"].get().strip()
        fields = self._collect_extract_fields()

        if not start_marker or not end_marker:
            messagebox.showerror(
                "Missing Range Criteria",
                "Define both the Range Start Marker and Range End Marker first.",
            )
            return False
        if not fields:
            messagebox.showerror("Missing Data Field", "Add at least one data field to extract.")
            return False
        return True

    def _collect_extract_fields(self):
        fields = []
        for row in self.extract_field_rows:
            widgets = row["widgets"]
            name = widgets["name"].get().strip()
            if not name:
                continue
            fields.append({
                "name": name,
                "row_marker": widgets["row_marker"].get().strip(),
                "from_word": widgets["from_word"].get().strip(),
                "pos_from": self._safe_int(widgets["pos_from"].get()),
                "pos_to": self._safe_int(widgets["pos_to"].get()),
                "end_word": widgets["end_word"].get().strip(),
            })
        return fields

    def _extract_value(self, line, from_word, pos_from, pos_to, end_word=""):
        if from_word:
            idx = line.find(from_word)
            if idx == -1:
                return ""
            start = idx + len(from_word) + max(pos_from, 0)
        else:
            start = max(pos_from, 0)

        if start > len(line):
            return ""

        end = len(line)
        if end_word:
            end_idx = line.find(end_word, start)
            if end_idx != -1:
                end = end_idx
        if pos_to and pos_to > 0:
            end = min(end, start + pos_to)
        if end <= start:
            return ""

        return line[start:end]

    def _extract_field_from_range(self, lines, field):
        row_marker = field.get("row_marker", "")
        source = next((line for line in lines if row_marker in line), "") if row_marker else "\n".join(lines)
        if row_marker and not source:
            return ""
        return self._extract_value(
            source, field.get("from_word", ""), field.get("pos_from", 0),
            field.get("pos_to", 0), field.get("end_word", ""),
        )

    def _run_extraction_tryout(self):
        if not self._require_extract_names():
            return

        log_path = self.settings_entries["LOG_FILE_PATH"].get().strip()
        if not log_path or not os.path.isfile(log_path):
            messagebox.showerror("Error", f"Log file not found:\n{log_path}")
            return

        start_marker = self.range_entries["start_marker"].get().strip()
        end_marker = self.range_entries["end_marker"].get().strip()
        fields = self._collect_extract_fields()

        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read log file:\n{str(e)}")
            return

        results = []
        pending_range = None

        for raw_line in lines:
            line = raw_line.rstrip("\n\r")

            if start_marker in line:
                pending_range = [line]
                if end_marker in line:
                    results.append({field["name"]: self._extract_field_from_range(pending_range, field) for field in fields})
                    pending_range = None
                continue

            if pending_range is not None:
                pending_range.append(line)
                if end_marker in line:
                    results.append({field["name"]: self._extract_field_from_range(pending_range, field) for field in fields})
                    pending_range = None

        self._display_json_tree(results)

    def _display_json_tree(self, data):
        self.extract_tree.delete(*self.extract_tree.get_children())

        if not data:
            self.extract_tree.insert("", "end", text="(no matches found)", values=("",))
            return

        self._populate_json_tree("", data)

        for node in self.extract_tree.get_children():
            self.extract_tree.item(node, open=True)

    def _populate_json_tree(self, parent_id, data):
        if isinstance(data, list):
            for i, item in enumerate(data):
                node = self.extract_tree.insert(parent_id, "end", text=f"[{i}]", values=("",))
                self._populate_json_tree(node, item)
        elif isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    node = self.extract_tree.insert(parent_id, "end", text=str(key), values=("",))
                    self._populate_json_tree(node, value)
                else:
                    self.extract_tree.insert(parent_id, "end", text=str(key), values=(str(value),))

    # --- TAB 2: AUTO SCRIPT (Slots + Actions) ---
    def _setup_auto_script_tab(self):
        outer = ttk.Frame(self.tab_auto_script)
        outer.pack(fill="both", expand=True, padx=0, pady=6)

        info = ttk.Label(
            outer,
            text=(
                "Defina a automação (PyAutoGUI) executada em cada Slot ao receber um código de barras. "
                "Cada Slot tem uma lista ordenada de Actions. Ações do tipo 'Click At Coordinates' têm "
                "sua própria coordenada X/Y (com botão de Captura) — um Slot pode ter várias ações de "
                "clique em sequência, cada uma em um ponto diferente."
            ),
            wraplength=600, justify="left",
        )
        info.pack(fill="x", pady=(0, 6))

        scroll_holder = tk.Frame(outer)
        scroll_holder.pack(fill="both", expand=True)
        _, self.slots_grid = self._make_scrollable(scroll_holder)

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(6, 0))
        self.btn_add_slot = ttk.Button(footer, text="+ Add Slot", command=self._on_add_slot)
        self.btn_add_slot.pack(side="left")

    # --- Slot card ---
    ACTIONS_TABLE_HEADERS = ["#", "On", "Type", "Details", ""]
    ACTIONS_TABLE_COL_WEIGHTS = [0, 0, 0, 1, 0]

    def _add_slot_card(self, slot_key, data=None):
        header = tk.Frame(self.slots_grid, bg=self.HEADER_BG)

        title_lbl = tk.Label(
            header, text=f"Slot {slot_key}", font=("Segoe UI", 9, "bold"), bg=self.HEADER_BG,
        )
        title_lbl.pack(side="left", padx=(4, 8), pady=1)

        enabled_var = tk.BooleanVar(value=True)
        enabled_chk = tk.Checkbutton(
            header, text="Enabled", variable=enabled_var, bg=self.HEADER_BG,
            command=lambda: self._apply_states(),
        )
        enabled_chk.pack(side="left", padx=(0, 8))

        delete_btn = tk.Button(
            header, text="🗑️ Delete Slot", bg=self.DANGER_BG, fg="white", relief="flat",
            command=lambda: self._delete_slot(slot_key),
        )
        delete_btn.pack(side="left", padx=(0, 4), pady=1)

        card = ttk.LabelFrame(self.slots_grid, labelwidget=header)
        card.pack(fill="x", expand=True, padx=4, pady=3)

        actions_table = tk.Frame(card, bg=self.GRID_LINE)
        actions_table.pack(fill="x", padx=4, pady=(4, 2))

        for col, htext in enumerate(self.ACTIONS_TABLE_HEADERS):
            tk.Label(
                actions_table, text=htext, font=self.HEADER_FONT, bg=self.HEADER_BG, fg="black",
                anchor="center", relief="flat",
            ).grid(row=0, column=col, padx=(0, 1), pady=(0, 1), ipady=2, sticky="nsew")

        for col, weight in enumerate(self.ACTIONS_TABLE_COL_WEIGHTS):
            actions_table.grid_columnconfigure(col, weight=weight)

        add_action_btn = ttk.Button(
            card, text="+ Add Action", command=lambda sk=slot_key: self._on_add_action(sk),
        )
        add_action_btn.pack(anchor="w", padx=4, pady=(0, 4))

        slot_entry = {
            "card": card, "header": header, "enabled_var": enabled_var, "enabled_check": enabled_chk,
            "delete_btn": delete_btn, "actions_table": actions_table, "add_action_btn": add_action_btn,
            "actions": [],
        }
        self.slot_entries[slot_key] = slot_entry

        if data:
            enabled_var.set(bool(data.get("enabled", True)))
            for action_data in data.get("actions", []):
                self._add_action_row(slot_key, action_data)

        return slot_entry

    def _on_add_slot(self):
        existing = [int(k) for k in self.slot_entries.keys() if k.isdigit()]
        next_slot = str(max(existing) + 1) if existing else "1"
        self._add_slot_card(next_slot)
        self._apply_states()

    def _delete_slot(self, slot_key):
        confirmed = messagebox.askyesno(
            "⚠️ Confirm Deletion",
            f"⚠️ WARNING: This will permanently delete Slot {slot_key} and ALL its actions.\n\n"
            "Are you sure you want to continue?",
            icon="warning",
        )
        if not confirmed:
            return
        self.slot_entries[slot_key]["card"].destroy()
        del self.slot_entries[slot_key]
        self._apply_states()

    def _rebuild_slots_grid(self, slots_dict):
        for slot in list(self.slot_entries.values()):
            slot["card"].destroy()
        self.slot_entries = {}

        keys = sorted(slots_dict.keys(), key=lambda k: int(k) if k.isdigit() else k) if slots_dict else []
        if not keys:
            keys = [str(i) for i in range(1, 9)]

        for key in keys:
            self._add_slot_card(key, slots_dict.get(key) if slots_dict else None)

    # --- Action row ---
    def _on_add_action(self, slot_key):
        self._add_action_row(slot_key)
        self._apply_states()

    def _add_action_row(self, slot_key, data=None):
        slot = self.slot_entries[slot_key]
        table = slot["actions_table"]
        row_index = len(slot["actions"]) + 1  # row 0 is the header

        num_label = tk.Label(table, text="", font=self.CELL_FONT, bg=self.ROW_BG, anchor="center")
        num_label.grid(row=row_index, column=0, padx=(0, 1), pady=(0, 1), ipady=2, sticky="nsew")

        enabled_cell = tk.Frame(table, bg=self.ROW_BG)
        enabled_cell.grid(row=row_index, column=1, padx=(0, 1), pady=(0, 1), sticky="nsew")
        enabled_var = tk.BooleanVar(value=True)
        enabled_chk = tk.Checkbutton(
            enabled_cell, variable=enabled_var, bg=self.ROW_BG, command=lambda: self._apply_states(),
        )
        enabled_chk.pack(expand=True, pady=1)

        type_var = tk.StringVar(value="None")
        combo = ttk.Combobox(table, textvariable=type_var, values=self.STEP_TYPES, state="readonly", width=17)
        combo.grid(row=row_index, column=2, padx=(0, 1), pady=(0, 1), sticky="nsew")

        details_cell = tk.Frame(table, bg=self.ROW_BG)
        details_cell.grid(row=row_index, column=3, padx=(0, 1), pady=(0, 1), sticky="nsew")

        delete_btn = tk.Button(
            table, text="🗑️", bg=self.DANGER_BG, fg="white", relief="flat",
        )
        delete_btn.grid(row=row_index, column=4, padx=(0, 1), pady=(0, 1), sticky="nsew")

        action = {
            "cells": [num_label, enabled_cell, combo, details_cell, delete_btn],
            "num_label": num_label, "enabled_var": enabled_var, "enabled_check": enabled_chk,
            "type_var": type_var, "combo": combo, "fields_frame": details_cell, "widgets": {},
            "delete_btn": delete_btn, "slot_key": slot_key,
        }

        combo.bind("<<ComboboxSelected>>", lambda e, a=action: self._refresh_action_fields(a))
        delete_btn.configure(command=lambda a=action: self._delete_action(a))

        slot["actions"].append(action)
        self._refresh_action_fields(action)
        self._renumber_actions(slot_key)

        if data:
            self._set_action_data(action, data)

        return action

    def _delete_action(self, action):
        slot_key = action["slot_key"]
        slot = self.slot_entries[slot_key]
        idx = slot["actions"].index(action) + 1

        confirmed = messagebox.askyesno(
            "⚠️ Confirm Deletion",
            f"⚠️ WARNING: This will permanently delete Action #{idx} from Slot {slot_key}.\n\n"
            "Are you sure you want to continue?",
            icon="warning",
        )
        if not confirmed:
            return

        for w in action["cells"]:
            w.destroy()
        slot["actions"].remove(action)
        self._regrid_actions(slot_key)
        self._apply_states()

    def _regrid_actions(self, slot_key):
        # Actions are grid rows (for the Excel-style thin borders), so after a
        # deletion the remaining rows must be shifted up to close the gap.
        slot = self.slot_entries[slot_key]
        for i, action in enumerate(slot["actions"], start=1):
            for w in action["cells"]:
                w.grid_configure(row=i)
        self._renumber_actions(slot_key)

    def _renumber_actions(self, slot_key):
        slot = self.slot_entries[slot_key]
        for i, action in enumerate(slot["actions"], start=1):
            action["num_label"].configure(text=str(i))

    def _refresh_action_fields(self, action):
        for w in action["fields_frame"].winfo_children():
            w.destroy()
        action["widgets"] = {}

        kind = action["type_var"].get()

        if kind == "Click At Coordinates":
            tk.Label(action["fields_frame"], text="X:", bg=self.ROW_BG, font=self.CELL_FONT).pack(side="left", padx=(4, 0))
            ex = tk.Entry(
                action["fields_frame"], width=5, justify="center", validate="key", validatecommand=self._int_vcmd,
            )
            ex.pack(side="left", padx=(2, 6), pady=2)
            tk.Label(action["fields_frame"], text="Y:", bg=self.ROW_BG, font=self.CELL_FONT).pack(side="left")
            ey = tk.Entry(
                action["fields_frame"], width=5, justify="center", validate="key", validatecommand=self._int_vcmd,
            )
            ey.pack(side="left", padx=(2, 6), pady=2)
            capture_btn = ttk.Button(
                action["fields_frame"], text="🎯 Capture",
                command=lambda ex=ex, ey=ey: self._start_capture_overlay(ex, ey, silent_save=True),
            )
            capture_btn.pack(side="left")
            action["widgets"] = {"x": ex, "y": ey, "capture_btn": capture_btn}

        elif kind == "Keyboard Typing":
            source_var = tk.StringVar(value="Received Barcode")
            source_combo = ttk.Combobox(
                action["fields_frame"], textvariable=source_var,
                values=["Received Barcode", "Custom Text"], state="readonly", width=16,
            )
            source_combo.pack(side="left", padx=(0, 8))

            text_entry = tk.Entry(action["fields_frame"], width=20)
            text_entry.pack(side="left")
            text_entry.configure(state="disabled")

            def _on_source_change(event=None, sv=source_var, te=text_entry):
                te.configure(state="normal" if sv.get() == "Custom Text" else "disabled")

            source_combo.bind("<<ComboboxSelected>>", _on_source_change)
            action["widgets"] = {"source_var": source_var, "source_combo": source_combo, "text_entry": text_entry}

        elif kind == "Press Key":
            key_var = tk.StringVar(value="Enter")
            key_combo = ttk.Combobox(
                action["fields_frame"], textvariable=key_var, values=self.KEY_OPTIONS, state="readonly", width=14,
            )
            key_combo.pack(side="left")
            action["widgets"] = {"key_var": key_var, "key_combo": key_combo}

        # kind == "None": nenhum campo adicional

    def _get_action_data(self, action):
        kind = action["type_var"].get()
        w = action["widgets"]
        base = {"enabled": bool(action["enabled_var"].get())}

        if kind == "Click At Coordinates":
            x_str = w["x"].get().strip()
            y_str = w["y"].get().strip()
            x_val = int(x_str) if x_str not in ("", "-") else 0
            y_val = int(y_str) if y_str not in ("", "-") else 0
            base.update({"type": "click", "x": x_val, "y": y_val})
        elif kind == "Keyboard Typing":
            if w["source_var"].get() == "Custom Text":
                base.update({"type": "type_text", "source": "custom", "text": w["text_entry"].get()})
            else:
                base.update({"type": "type_text", "source": "barcode"})
        elif kind == "Press Key":
            base.update({"type": "key_press", "key": self.KEY_VALUE_MAP.get(w["key_var"].get(), "enter")})
        else:
            base["type"] = "none"

        return base

    def _set_action_data(self, action, data):
        kind = data.get("type", "none")
        action["type_var"].set(self.STEP_TYPE_TO_LABEL.get(kind, "None"))
        action["enabled_var"].set(bool(data.get("enabled", True)))
        self._refresh_action_fields(action)

        if kind == "click":
            action["widgets"]["x"].insert(0, str(data.get("x", 0)))
            action["widgets"]["y"].insert(0, str(data.get("y", 0)))
        elif kind == "type_text":
            if data.get("source") == "custom":
                action["widgets"]["source_var"].set("Custom Text")
                action["widgets"]["text_entry"].configure(state="normal")
                action["widgets"]["text_entry"].insert(0, data.get("text", ""))
            else:
                action["widgets"]["source_var"].set("Received Barcode")
        elif kind == "key_press":
            action["widgets"]["key_var"].set(self.KEY_LABEL_MAP.get(data.get("key", "enter"), "Enter"))

    # --- JSON STORAGE ---
    def _collect_settings_payload(self):
        payload = {
            "SERVER_HOST_IP": self.settings_entries["SERVER_HOST_IP"].get().strip(),
            "SERVER_PORT": int(self.settings_entries["SERVER_PORT"].get().strip()),
            "TARGET_WINDOW_TITLE": self.settings_entries["TARGET_WINDOW_TITLE"].get().strip(),
            "MAIN_PROCESS_FILE": self.settings_entries["MAIN_PROCESS_FILE"].get().strip() or "main.py",
            "LOG_FILE_PATH": self.settings_entries["LOG_FILE_PATH"].get().strip(),
            "LOG_EXTRACT": {
                "range": {
                    "start_marker": self.range_entries["start_marker"].get().strip(),
                    "end_marker": self.range_entries["end_marker"].get().strip(),
                },
                "fields": self._collect_extract_fields(),
            },
            "SLOTS": {},
        }

        for slot_key, slot in self.slot_entries.items():
            payload["SLOTS"][slot_key] = {
                "enabled": bool(slot["enabled_var"].get()),
                "actions": [self._get_action_data(action) for action in slot["actions"]],
            }

        return payload

    def load_config(self):
        default_data = {
            "SERVER_HOST_IP": "127.0.0.1",
            "SERVER_PORT": 8000,
            "TARGET_WINDOW_TITLE": "Untitled - Notepad",
            "MAIN_PROCESS_FILE": "main.py",
            "LOG_FILE_PATH": "",
            "LOG_EXTRACT": {
                "range": {"start_marker": "", "end_marker": ""},
                "fields": [],
            },
            "SLOTS": {},
        }

        if os.path.exists(self.config_filename):
            try:
                with open(self.config_filename, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_data.update(data)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load JSON:\n{str(e)}")
                return

        self.settings_entries["SERVER_HOST_IP"].delete(0, tk.END)
        self.settings_entries["SERVER_HOST_IP"].insert(0, str(default_data.get("SERVER_HOST_IP", "")))

        self.settings_entries["SERVER_PORT"].delete(0, tk.END)
        self.settings_entries["SERVER_PORT"].insert(0, str(default_data.get("SERVER_PORT", 8000)))

        self.settings_entries["TARGET_WINDOW_TITLE"].delete(0, tk.END)
        self.settings_entries["TARGET_WINDOW_TITLE"].insert(0, str(default_data.get("TARGET_WINDOW_TITLE", "")))

        self.settings_entries["MAIN_PROCESS_FILE"].delete(0, tk.END)
        self.settings_entries["MAIN_PROCESS_FILE"].insert(0, str(default_data.get("MAIN_PROCESS_FILE", "main.py")))

        self.settings_entries["LOG_FILE_PATH"].delete(0, tk.END)
        self.settings_entries["LOG_FILE_PATH"].insert(0, str(default_data.get("LOG_FILE_PATH", "")))

        log_extract = default_data.get("LOG_EXTRACT", {}) or {}
        range_data = log_extract.get("range", {}) or {}
        if not range_data and (log_extract.get("start") or log_extract.get("end")):
            old_start = log_extract.get("start", {}) or {}
            old_end = log_extract.get("end", {}) or {}
            range_data = {
                "start_marker": old_start.get("row_marker", ""),
                "end_marker": old_end.get("row_marker", ""),
            }
            fields_data = [old_start, old_end]
        else:
            fields_data = log_extract.get("fields", []) or []

        for key in ("start_marker", "end_marker"):
            self.range_entries[key].delete(0, tk.END)
            self.range_entries[key].insert(0, str(range_data.get(key, "")))

        for row in list(self.extract_field_rows):
            self._delete_extract_field(row)
        for field_data in fields_data:
            self._on_add_extract_field(field_data)

        self._rebuild_slots_grid(default_data.get("SLOTS", {}))

        # Baseline for dirty-tracking: whatever is on disk right now counts
        # as "saved", so Save starts disabled until the user actually changes something.
        self._last_saved_payload = self._collect_settings_payload()
        self._dirty = False

        self._apply_states()

    def save_config(self, silent=False):
        if not self._require_extract_names():
            return

        try:
            payload = self._collect_settings_payload()

            with open(self.config_filename, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=4)

            self._last_saved_payload = payload
            self._dirty = False
            self._update_run_controls()

            if not silent:
                messagebox.showinfo("Success", "Configuration saved successfully!")

        except ValueError:
            if not silent:
                messagebox.showerror("Validation Error", "PORT and every Click At Coordinates X/Y must be valid integers.")
        except Exception as e:
            if not silent:
                messagebox.showerror("Save Error", f"An unexpected error occurred:\n{str(e)}")

if __name__ == "__main__":
    app = SetupApp()
    app.mainloop()
