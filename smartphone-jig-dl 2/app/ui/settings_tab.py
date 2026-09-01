import tkinter as tk
from tkinter import scrolledtext, ttk

from infra import window_picker

from . import tk_helpers as ui


class SettingsTab(ttk.Frame):
    """Aba 'Server Settings': host/porta/janela-alvo/processo principal, e o
    console de saída do processo supervisionado."""

    def __init__(self, parent, request_silent_save):
        super().__init__(parent)
        self.request_silent_save = request_silent_save
        self.entries = {}
        self._build()

    def _build(self):
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=0, pady=8)

        settings_table = tk.Frame(container, bg=ui.GRID_LINE)
        settings_table.pack(fill="x")

        def _add_settings_row(row, label_text, build_cell):
            tk.Label(
                settings_table, text=label_text, font=ui.HEADER_FONT, bg=ui.HEADER_BG,
                anchor="w",
            ).grid(row=row, column=0, padx=(0, 1), pady=(0, 1), ipady=4, ipadx=6, sticky="nsew")

            cell = tk.Frame(settings_table, bg=ui.ROW_BG)
            cell.grid(row=row, column=1, padx=(0, 1), pady=(0, 1), sticky="nsew")
            build_cell(cell)

        def _build_host(cell):
            self.entries["SERVER_HOST_IP"] = tk.Entry(cell, width=30)
            self.entries["SERVER_HOST_IP"].pack(side="left", padx=4, pady=3)

        def _build_port(cell):
            self.entries["SERVER_PORT"] = tk.Entry(cell, width=30)
            self.entries["SERVER_PORT"].pack(side="left", padx=4, pady=3)

        def _build_window(cell):
            self.entries["TARGET_WINDOW_TITLE"] = tk.Entry(cell, width=22)
            self.entries["TARGET_WINDOW_TITLE"].pack(side="left", padx=(4, 6), pady=3)
            self.btn_window_picker = ttk.Button(
                cell, text="🪟 Pick Window", command=self._start_window_picker,
            )
            self.btn_window_picker.pack(side="left")

        _add_settings_row(0, "SERVER_HOST_IP", _build_host)
        _add_settings_row(1, "SERVER_PORT", _build_port)
        _add_settings_row(2, "TARGET_WINDOW_TITLE", _build_window)

        settings_table.grid_columnconfigure(0, weight=0)
        settings_table.grid_columnconfigure(1, weight=1)

        ttk.Label(
            container, text="Server Output:", font=("Segoe UI", 9, "bold"),
        ).pack(fill="x", pady=(0, 2))

        self.console_output = scrolledtext.ScrolledText(
            container, height=4, width=50, state="disabled", wrap="word",
            bg="#1e1e1e", fg="#d4d4d4", insertbackground="#d4d4d4", font=("Consolas", 9),
        )
        self.console_output.pack(fill="both", expand=True)

    # --- payload / state ---
    def get_payload(self):
        return {
            "SERVER_HOST_IP": self.entries["SERVER_HOST_IP"].get().strip(),
            "SERVER_PORT": int(self.entries["SERVER_PORT"].get().strip()),
            "TARGET_WINDOW_TITLE": self.entries["TARGET_WINDOW_TITLE"].get().strip(),
        }

    def apply_data(self, data):
        for key, default in (
            ("SERVER_HOST_IP", ""), ("SERVER_PORT", 8000),
            ("TARGET_WINDOW_TITLE", ""),
        ):
            entry = self.entries[key]
            entry.delete(0, tk.END)
            entry.insert(0, str(data.get(key, default)))

    def get_target_window_title(self):
        return self.entries["TARGET_WINDOW_TITLE"].get().strip()

    def set_locked(self, locked):
        state = "disabled" if locked else "normal"
        for entry in self.entries.values():
            entry.configure(state=state)
        self.btn_window_picker.configure(state=state)

    def append_console_line(self, text):
        self.console_output.configure(state="normal")
        self.console_output.insert("end", text + "\n")
        self.console_output.see("end")
        self.console_output.configure(state="disabled")

    # --- window picker ---
    def _start_window_picker(self):
        self.btn_window_picker.configure(text="🔴 Hover & Click...", state="disabled")

        entry = self.entries["TARGET_WINDOW_TITLE"]

        def on_hover(title):
            state_before = entry.cget("state")
            entry.configure(state="normal")
            entry.delete(0, tk.END)
            entry.insert(0, title)
            entry.configure(state=state_before)

        def on_confirmed():
            self.btn_window_picker.configure(text="🪟 Pick Window", state="normal")
            self.request_silent_save()

        def on_cancelled():
            self.btn_window_picker.configure(text="🪟 Pick Window", state="normal")

        window_picker.pick_window_title(
            self.winfo_toplevel(), self.winfo_toplevel().title(),
            on_hover, on_confirmed, on_cancelled,
        )
