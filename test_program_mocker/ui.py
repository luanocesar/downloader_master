import json
import os
import re
import sys
import subprocess
import tkinter as tk
from tkinter import messagebox, ttk
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

    def __init__(self, config_filename="config.json"):
        super().__init__()
        self.title("Downloader App - Configuration Manager")
        self.geometry("820x700")
        self.minsize(700, 520)
        self.config_filename = config_filename

        self._int_vcmd = (self.register(self._validate_integer_input), "%P")

        self.settings_entries = {}
        self.slot_entries = {}
        self.server_process = None
        self._locked = False

        self._init_ui()
        self.load_config()

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

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

        # --- FOOTER ---
        footer = ttk.Frame(self)
        footer.pack(fill="x", side="bottom", padx=8, pady=6)

        self.btn_toggle = tk.Button(
            footer,
            text="STATUS: OFF",
            bg="#e57373",
            fg="white",
            font=("Segoe UI", 12, "bold"),
            width=15,
            command=self.toggle_server
        )
        self.btn_toggle.pack(side="left")

        self.btn_save = ttk.Button(footer, text="Save Configuration", command=self.save_config)
        self.btn_save.pack(side="right", padx=5)

        self.btn_reload = ttk.Button(footer, text="Reload", command=self.load_config)
        self.btn_reload.pack(side="right")

    # --- SHARED HELPERS ---
    def _validate_integer_input(self, proposed):
        if proposed in ("", "-"):
            return True
        return bool(re.fullmatch(r"-?\d+", proposed))

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
    def toggle_server(self):
        if self.server_process is None:
            try:
                self.server_process = subprocess.Popen([sys.executable, "main.py"])
                self.btn_toggle.configure(text="STATUS: ON", bg="yellowgreen", fg="black")
                self._locked = True
                self._apply_states()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to start main.py:\n{str(e)}")
        else:
            self.server_process.terminate()
            self.server_process = None
            self.btn_toggle.configure(text="STATUS: OFF", bg="#e57373", fg="white")
            self._locked = False
            self._apply_states()

    def _apply_states(self):
        """Recomputes the enabled/disabled state of every widget based on
        whether the server is running (locked) and each Slot's/Action's own
        enabled checkbox."""
        global_state = "disabled" if self._locked else "normal"

        for entry in self.settings_entries.values():
            if isinstance(entry, ttk.Entry):
                entry.configure(state=global_state)

        self.btn_window_picker.configure(state=global_state)
        self.btn_save.configure(state=global_state)
        self.btn_reload.configure(state=global_state)
        self.btn_add_slot.configure(state=global_state)

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

    def on_closing(self):
        if self.server_process is not None:
            self.server_process.terminate()
        self.destroy()

    # --- TAB 1: SERVER SETTINGS ---
    def _setup_settings_tab(self):
        container = ttk.Frame(self.tab_settings)
        container.pack(fill="both", expand=True, padx=14, pady=12)

        ttk.Label(container, text="SERVER_HOST_IP:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, pady=6, sticky="w")
        self.settings_entries["SERVER_HOST_IP"] = ttk.Entry(container, width=30)
        self.settings_entries["SERVER_HOST_IP"].grid(row=0, column=1, padx=8, pady=6, sticky="w")

        ttk.Label(container, text="SERVER_PORT:", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, pady=6, sticky="w")
        self.settings_entries["SERVER_PORT"] = ttk.Entry(container, width=30)
        self.settings_entries["SERVER_PORT"].grid(row=1, column=1, padx=8, pady=6, sticky="w")

        ttk.Label(container, text="TARGET_WINDOW_TITLE:", font=("Segoe UI", 9, "bold")).grid(row=2, column=0, pady=6, sticky="w")

        target_frame = ttk.Frame(container)
        target_frame.grid(row=2, column=1, padx=8, pady=6, sticky="w")

        self.settings_entries["TARGET_WINDOW_TITLE"] = ttk.Entry(target_frame, width=30)
        self.settings_entries["TARGET_WINDOW_TITLE"].pack(side="left")

        self.btn_window_picker = ttk.Button(
            target_frame,
            text="🪟 Pick Window",
            command=self._start_window_picker
        )
        self.btn_window_picker.pack(side="left", padx=(5, 0))

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

    # --- TAB 2: AUTO SCRIPT (Slots + Actions) ---
    def _setup_auto_script_tab(self):
        outer = ttk.Frame(self.tab_auto_script)
        outer.pack(fill="both", expand=True, padx=8, pady=6)

        info = ttk.Label(
            outer,
            text=(
                "Defina a automação (PyAutoGUI) executada em cada Slot ao receber um código de barras. "
                "Cada Slot tem uma lista ordenada de Actions. Ações do tipo 'Click At Coordinates' têm "
                "sua própria coordenada X/Y (com botão de Captura) — um Slot pode ter várias ações de "
                "clique em sequência, cada uma em um ponto diferente."
            ),
            wraplength=760, justify="left",
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

        self._rebuild_slots_grid(default_data.get("SLOTS", {}))
        self._apply_states()

    def save_config(self, silent=False):
        try:
            payload = self._collect_settings_payload()

            with open(self.config_filename, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=4)

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
