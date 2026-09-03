import tkinter as tk
from tkinter import messagebox, ttk

from infra import window_picker

from . import tk_helpers as ui


class AutoScriptTab(ttk.Frame):
    """Aba 'Auto Script': lista de Slots, cada um com sua sequência ordenada
    de Actions (clique/digitação/tecla) executada ao receber um código de
    barras."""

    STEP_TYPES = ["None", "Click At Coordinates", "Double-Click At Coordinates", "Keyboard Typing", "Press Key"]
    COORDINATE_LABELS = ("Click At Coordinates", "Double-Click At Coordinates")
    KEY_OPTIONS = ["Enter", "Tab", "Spacebar", "Backspace"]
    KEY_VALUE_MAP = {"Enter": "enter", "Tab": "tab", "Spacebar": "space", "Backspace": "backspace"}
    KEY_LABEL_MAP = {v: k for k, v in KEY_VALUE_MAP.items()}
    STEP_TYPE_TO_LABEL = {
        "none": "None", "click": "Click At Coordinates", "double_click": "Double-Click At Coordinates",
        "type_text": "Keyboard Typing", "key_press": "Press Key",
    }

    ACTIONS_TABLE_HEADERS = ["#", "On", "Type", "Details", ""]
    ACTIONS_TABLE_COL_WEIGHTS = [0, 0, 0, 1, 0]

    def __init__(
        self, parent, int_vcmd, get_target_window_title,
        get_active_script_name, on_open_script, on_save_as_script,
    ):
        super().__init__(parent)
        self._int_vcmd = int_vcmd
        self.get_target_window_title = get_target_window_title
        self._get_active_script_name = get_active_script_name
        self._open_script = on_open_script
        self._save_script_as = on_save_as_script
        self.slot_entries = {}
        self._locked = False
        self._build()
        self.refresh_script_display()

    def _build(self):
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=0, pady=6)

        script_row = tk.Frame(outer, bg=ui.GRID_LINE)
        script_row.pack(fill="x", pady=(0, 8))

        tk.Label(
            script_row, text="SCRIPT FILE", font=ui.HEADER_FONT, bg=ui.HEADER_BG,
            anchor="w",
        ).grid(row=0, column=0, padx=(0, 1), pady=(0, 1), ipady=4, ipadx=6, sticky="nsew")

        script_cell = tk.Frame(script_row, bg=ui.ROW_BG)
        script_cell.grid(row=0, column=1, padx=(0, 1), pady=(0, 1), sticky="nsew")

        self.script_path_entry = tk.Entry(script_cell, width=24, state="readonly")
        self.script_path_entry.pack(side="left", padx=(4, 6), pady=3, fill="x", expand=True)

        self.btn_open_script = ttk.Button(script_cell, text="📂 Open Script...", command=self._on_open_script)
        self.btn_open_script.pack(side="left", padx=(0, 4))

        self.btn_save_as_script = ttk.Button(script_cell, text="💾 Save Script As...", command=self._on_save_as_script)
        self.btn_save_as_script.pack(side="left")

        script_row.grid_columnconfigure(0, weight=0)
        script_row.grid_columnconfigure(1, weight=1)

        info = ttk.Label(
            outer,
            text=(
                "Defina a automação (PyAutoGUI) executada em cada Slot ao receber um código de barras. "
                "Cada Slot tem uma lista ordenada de Actions. Ações do tipo 'Click At Coordinates' e "
                "'Double-Click At Coordinates' têm sua própria coordenada X/Y (com botão de Captura) — "
                "um Slot pode ter várias ações de clique em sequência, cada uma em um ponto diferente."
            ),
            wraplength=600, justify="left",
        )
        info.pack(fill="x", pady=(0, 6))

        scroll_holder = tk.Frame(outer)
        scroll_holder.pack(fill="both", expand=True)
        _, self.slots_grid = ui.make_scrollable(scroll_holder)

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(6, 0))
        self.btn_add_slot = ttk.Button(footer, text="+ Add Slot", command=self._on_add_slot)
        self.btn_add_slot.pack(side="left")

    # --- Slot card ---
    def _add_slot_card(self, slot_key, data=None):
        header = tk.Frame(self.slots_grid, bg=ui.HEADER_BG)

        title_lbl = tk.Label(
            header, text=f"Slot {slot_key}", font=("Segoe UI", 9, "bold"), bg=ui.HEADER_BG,
        )
        title_lbl.pack(side="left", padx=(4, 8), pady=1)

        enabled_var = tk.BooleanVar(value=True)
        enabled_chk = tk.Checkbutton(
            header, text="Enabled", variable=enabled_var, bg=ui.HEADER_BG,
            command=self._apply_local_states,
        )
        enabled_chk.pack(side="left", padx=(0, 8))

        delete_btn = tk.Button(
            header, text="🗑️ Delete Slot", bg=ui.DANGER_BG, fg="white", relief="flat",
            command=lambda: self._delete_slot(slot_key),
        )
        delete_btn.pack(side="left", padx=(0, 4), pady=1)

        card = ttk.LabelFrame(self.slots_grid, labelwidget=header)
        card.pack(fill="x", expand=True, padx=4, pady=3)

        actions_table = tk.Frame(card, bg=ui.GRID_LINE)
        actions_table.pack(fill="x", padx=4, pady=(4, 2))

        for col, htext in enumerate(self.ACTIONS_TABLE_HEADERS):
            tk.Label(
                actions_table, text=htext, font=ui.HEADER_FONT, bg=ui.HEADER_BG, fg="black",
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
        self._apply_local_states()

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
        self._apply_local_states()

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
        self._apply_local_states()

    def _add_action_row(self, slot_key, data=None):
        slot = self.slot_entries[slot_key]
        table = slot["actions_table"]
        row_index = len(slot["actions"]) + 1  # row 0 is the header

        num_label = tk.Label(table, text="", font=ui.CELL_FONT, bg=ui.ROW_BG, anchor="center")
        num_label.grid(row=row_index, column=0, padx=(0, 1), pady=(0, 1), ipady=2, sticky="nsew")

        enabled_cell = tk.Frame(table, bg=ui.ROW_BG)
        enabled_cell.grid(row=row_index, column=1, padx=(0, 1), pady=(0, 1), sticky="nsew")
        enabled_var = tk.BooleanVar(value=True)
        enabled_chk = tk.Checkbutton(
            enabled_cell, variable=enabled_var, bg=ui.ROW_BG, command=self._apply_local_states,
        )
        enabled_chk.pack(expand=True, pady=1)

        type_var = tk.StringVar(value="None")
        combo = ttk.Combobox(table, textvariable=type_var, values=self.STEP_TYPES, state="readonly", width=17)
        combo.grid(row=row_index, column=2, padx=(0, 1), pady=(0, 1), sticky="nsew")

        details_cell = tk.Frame(table, bg=ui.ROW_BG)
        details_cell.grid(row=row_index, column=3, padx=(0, 1), pady=(0, 1), sticky="nsew")

        delete_btn = tk.Button(
            table, text="🗑️", bg=ui.DANGER_BG, fg="white", relief="flat",
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
        self._apply_local_states()

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

        if kind in self.COORDINATE_LABELS:
            self._build_coordinate_fields(action)

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

    def _build_coordinate_fields(self, action):
        tk.Label(action["fields_frame"], text="X:", bg=ui.ROW_BG, font=ui.CELL_FONT).pack(side="left", padx=(4, 0))
        ex = tk.Entry(
            action["fields_frame"], width=5, justify="center", validate="key", validatecommand=self._int_vcmd,
        )
        ex.pack(side="left", padx=(2, 6), pady=2)
        tk.Label(action["fields_frame"], text="Y:", bg=ui.ROW_BG, font=ui.CELL_FONT).pack(side="left")
        ey = tk.Entry(
            action["fields_frame"], width=5, justify="center", validate="key", validatecommand=self._int_vcmd,
        )
        ey.pack(side="left", padx=(2, 6), pady=2)
        capture_btn = ttk.Button(
            action["fields_frame"], text="🎯 Capture",
            command=lambda ex=ex, ey=ey: self._start_coordinate_capture(ex, ey),
        )
        capture_btn.pack(side="left")
        action["widgets"] = {"x": ex, "y": ey, "capture_btn": capture_btn}

    def _start_coordinate_capture(self, ex, ey):
        target_title = self.get_target_window_title()

        if not target_title:
            messagebox.showerror("Erro", "Defina o TARGET_WINDOW_TITLE na aba 'Server Settings' primeiro.")
            return

        def on_captured(x, y):
            # Just fills the fields like a manual edit would -- the normal
            # dirty-tracking poll picks it up and lights up Save. A silent
            # auto-save here used to clear the dirty flag immediately, so a
            # capture (including a re-capture correcting an earlier one)
            # never visibly registered as a pending change.
            ex.delete(0, tk.END)
            ex.insert(0, str(x))
            ey.delete(0, tk.END)
            ey.insert(0, str(y))

        def on_error(title, message):
            messagebox.showerror(title, message)

        window_picker.capture_click_coordinates(self.winfo_toplevel(), target_title, on_captured, on_error)

    def _get_action_data(self, action):
        kind = action["type_var"].get()
        w = action["widgets"]
        base = {"enabled": bool(action["enabled_var"].get())}

        if kind in self.COORDINATE_LABELS:
            x_str = w["x"].get().strip()
            y_str = w["y"].get().strip()
            x_val = int(x_str) if x_str not in ("", "-") else 0
            y_val = int(y_str) if y_str not in ("", "-") else 0
            a_type = "double_click" if kind == "Double-Click At Coordinates" else "click"
            base.update({"type": a_type, "x": x_val, "y": y_val})
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

        if kind in ("click", "double_click"):
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

    # --- payload / state ---
    def get_payload(self):
        slots = {}
        for slot_key, slot in self.slot_entries.items():
            slots[slot_key] = {
                "enabled": bool(slot["enabled_var"].get()),
                "actions": [self._get_action_data(action) for action in slot["actions"]],
            }
        return {"SLOTS": slots}

    def apply_data(self, slots_dict):
        self._rebuild_slots_grid(slots_dict)
        self._apply_local_states()

    def set_locked(self, locked):
        self._locked = locked
        self._apply_local_states()

    # --- script file field ---
    def refresh_script_display(self):
        self.script_path_entry.configure(state="normal")
        self.script_path_entry.delete(0, tk.END)
        self.script_path_entry.insert(0, self._get_active_script_name())
        self.script_path_entry.configure(state="readonly")

    def _on_open_script(self):
        self._open_script()
        self.refresh_script_display()

    def _on_save_as_script(self):
        self._save_script_as()
        self.refresh_script_display()

    def _apply_local_states(self):
        global_state = "disabled" if self._locked else "normal"
        self.btn_add_slot.configure(state=global_state)
        self.btn_open_script.configure(state=global_state)
        self.btn_save_as_script.configure(state=global_state)

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
