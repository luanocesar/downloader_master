import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core import log_extractor

from . import config_editor
from . import tk_helpers as ui


class LogFileTab(ttk.Frame):
    """Aba 'Log File': caminho do log, critério de range e campos a extrair,
    com um 'Try Out' que roda a extração contra o arquivo real."""

    EXTRACT_FIELD_HEADERS = [
        "Field Name", "String Marker (Optional)", "Start String (optional)",
        "Start", "Size", "End String (Optional)", "",
    ]
    EXTRACT_FIELD_KEYS = ("name", "row_marker", "from_word", "pos_from", "pos_to", "end_word")

    def __init__(self, parent, int_vcmd):
        super().__init__(parent)
        self._int_vcmd = int_vcmd
        self.range_entries = {}
        self.extract_field_rows = []
        self._build()

    def _build(self):
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=0, pady=8)

        log_table = tk.Frame(container, bg=ui.GRID_LINE)
        log_table.pack(fill="x")

        tk.Label(
            log_table, text="LOG_FILE_PATH", font=ui.HEADER_FONT, bg=ui.HEADER_BG, anchor="w",
        ).grid(row=0, column=0, padx=(0, 1), pady=(0, 1), ipady=4, ipadx=6, sticky="nsew")

        cell = tk.Frame(log_table, bg=ui.ROW_BG)
        cell.grid(row=0, column=1, padx=(0, 1), pady=(0, 1), sticky="nsew")

        self.log_path_entry = tk.Entry(cell, width=40)
        self.log_path_entry.pack(side="left", padx=4, pady=3, fill="x", expand=True)

        self.btn_log_picker = ttk.Button(cell, text="📁 Browse...", command=self._pick_log_file)
        self.btn_log_picker.pack(side="left", padx=(6, 4), pady=3)

        log_table.grid_columnconfigure(0, weight=0)
        log_table.grid_columnconfigure(1, weight=1)

        ttk.Label(
            container,
            text="LOG_FILE_PATH is the location of the log file the application should read/monitor.",
            font=("Segoe UI", 8), foreground="#555555",
        ).pack(fill="x", pady=(2, 8))

        ttk.Label(
            container,
            text=(
                "The range markers define one data context per barcode. Each field below is then "
                "extracted from that context. A field can optionally select a row, start after a "
                "reference word, and stop at a numeric or string position."
            ),
            wraplength=600, justify="left", font=("Segoe UI", 8), foreground="#555555",
        ).pack(fill="x", pady=(0, 6))

        range_group = ttk.LabelFrame(container, text="1. Data Range Criteria")
        range_group.pack(fill="x", pady=(0, 8))
        range_table = tk.Frame(range_group, bg=ui.GRID_LINE)
        range_table.pack(fill="x", padx=4, pady=4)

        for row, label, key in (
            (0, "Range Start Marker", "start_marker"),
            (1, "Range End Marker", "end_marker"),
        ):
            tk.Label(
                range_table, text=label, font=ui.HEADER_FONT, bg=ui.HEADER_BG, anchor="w",
            ).grid(row=row, column=0, padx=(0, 1), pady=(0, 1), ipady=4, ipadx=6, sticky="nsew")
            entry = tk.Entry(range_table)
            entry.grid(row=row, column=1, padx=(0, 1), pady=(0, 1), ipady=3, sticky="ew")
            self.range_entries[key] = entry
        range_table.grid_columnconfigure(1, weight=1)

        fields_group = ttk.LabelFrame(container, text="2. Data Fields to Extract")
        fields_group.pack(fill="x", pady=(0, 8))
        self.extract_fields_table = tk.Frame(fields_group, bg=ui.GRID_LINE)
        self.extract_fields_table.pack(fill="x", padx=4, pady=(4, 2))
        for column, title in enumerate(self.EXTRACT_FIELD_HEADERS):
            tk.Label(
                self.extract_fields_table, text=title, font=ui.HEADER_FONT,
                bg=ui.HEADER_BG, anchor="center",
            ).grid(row=0, column=column, padx=(0, 1), pady=(0, 1), ipady=3, sticky="nsew")
        for column, weight in enumerate((1, 2, 2, 0, 0, 2, 0)):
            self.extract_fields_table.grid_columnconfigure(column, weight=weight)

        fields_footer = ttk.Frame(fields_group)
        fields_footer.pack(fill="x", padx=4, pady=(0, 4))
        self.btn_add_extract_field = ttk.Button(
            fields_footer, text="+ Add Field", command=self._on_add_extract_field,
        )
        self.btn_add_extract_field.pack(side="left")

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

    # --- extract field rows CRUD ---
    def _on_add_extract_field(self, data=None):
        row_index = len(self.extract_field_rows) + 1
        table = self.extract_fields_table
        widgets = {}
        for column, key in enumerate(self.EXTRACT_FIELD_KEYS):
            entry = tk.Entry(
                table, width=8 if key in ("pos_from", "pos_to") else 16,
                validate="key" if key in ("pos_from", "pos_to") else None,
                validatecommand=self._int_vcmd if key in ("pos_from", "pos_to") else None,
                font=ui.CELL_FONT, bg=ui.ROW_BG, relief="flat", bd=0, highlightthickness=0,
            )
            entry.grid(row=row_index, column=column, padx=(0, 1), pady=(0, 1), ipady=3, sticky="ew")
            widgets[key] = entry

        delete_btn = tk.Button(
            table, text="X", bg=ui.DANGER_BG, fg="white", relief="flat", bd=0, highlightthickness=0,
            command=lambda: self._delete_extract_field(row),
        )
        delete_btn.grid(row=row_index, column=6, padx=(0, 1), pady=(0, 1), sticky="nsew")
        row = {"widgets": widgets, "delete_btn": delete_btn}
        self.extract_field_rows.append(row)

        if data:
            for key, entry in widgets.items():
                value = data.get(key, 0) if key in ("pos_from", "pos_to") else data.get(key, "")
                if value not in (None, ""):
                    entry.insert(0, str(value))

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

    def _pick_log_file(self):
        current = self.log_path_entry.get().strip()
        current_dir = os.path.dirname(current) if current else ""
        initial_dir = current_dir if current_dir and os.path.isdir(current_dir) else os.getcwd()

        selected = filedialog.askopenfilename(
            title="Select Log File",
            initialdir=initial_dir,
            filetypes=[("Log files", "*.log *.txt"), ("All files", "*.*")],
        )

        if selected:
            self.log_path_entry.delete(0, tk.END)
            self.log_path_entry.insert(0, selected)

    # --- extraction tryout ---
    def validate(self):
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
                "pos_from": ui.safe_int(widgets["pos_from"].get()),
                "pos_to": ui.safe_int(widgets["pos_to"].get()),
                "end_word": widgets["end_word"].get().strip(),
            })
        return fields

    def _run_extraction_tryout(self):
        if not self.validate():
            return

        log_path = self.log_path_entry.get().strip()
        if not log_path or not os.path.isfile(log_path):
            messagebox.showerror("Error", f"Log file not found:\n{log_path}")
            return

        start_marker = self.range_entries["start_marker"].get().strip()
        end_marker = self.range_entries["end_marker"].get().strip()
        fields = self._collect_extract_fields()

        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = [raw_line.rstrip("\n\r") for raw_line in f.readlines()]
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read log file:\n{str(e)}")
            return

        results = log_extractor.run_extraction(lines, start_marker, end_marker, fields)
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

    # --- payload / state ---
    def get_payload(self):
        return {
            "LOG_FILE_PATH": self.log_path_entry.get().strip(),
            "LOG_EXTRACT": {
                "range": {
                    "start_marker": self.range_entries["start_marker"].get().strip(),
                    "end_marker": self.range_entries["end_marker"].get().strip(),
                },
                "fields": self._collect_extract_fields(),
            },
        }

    def apply_data(self, data):
        self.log_path_entry.delete(0, tk.END)
        self.log_path_entry.insert(0, str(data.get("LOG_FILE_PATH", "")))

        range_data, fields_data = config_editor.normalize_log_extract(data.get("LOG_EXTRACT", {}))

        for key in ("start_marker", "end_marker"):
            self.range_entries[key].delete(0, tk.END)
            self.range_entries[key].insert(0, str(range_data.get(key, "")))

        for row in list(self.extract_field_rows):
            self._delete_extract_field(row)
        for field_data in fields_data:
            self._on_add_extract_field(field_data)

    def set_locked(self, locked):
        state = "disabled" if locked else "normal"
        self.log_path_entry.configure(state=state)
        self.btn_log_picker.configure(state=state)
        for entry in self.range_entries.values():
            entry.configure(state=state)
        for row in self.extract_field_rows:
            for entry in row["widgets"].values():
                entry.configure(state=state)
            row["delete_btn"].configure(state=state)
        self.btn_add_extract_field.configure(state=state)
