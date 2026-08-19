import csv
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

ctk.set_appearance_mode("dark")
BG_COLOR = "#20212b"
FRAME_COLOR = "#151720"
ACCENT_COLOR = "#7452ff"
HOVER_COLOR = "#5a3be0"

# --- EXCEL STYLING ---
HEADER_BG = "#b0b0b0"       # Dark silver / gray
HEADER_TEXT = "#000000"     # Black header text
CELL_BG = "#ffffff"         # White cells
CELL_TEXT = "#000000"       # Black cell text
GRID_LINE_COLOR = "#d4d4d4" # 1px Light Gray lines
DIRTY_COLOR = "#ffcc80"     # Orange warning for unsaved changes
TEXT_COLOR = "#ffffff"      # General UI text (Labels outside the grid)


class SpreadsheetGrid(ctk.CTkFrame):
    def __init__(self, master, headers, col_widths, data_keys, **kwargs):
        super().__init__(master, fg_color="transparent", corner_radius=0, **kwargs)
        self.headers = headers
        self.col_widths = col_widths
        self.data_keys = data_keys
        self.rows = []
        
        # Outer Border wrapper to provide the leftmost and topmost 1px grid line
        self.border_frame = ctk.CTkFrame(self, fg_color=GRID_LINE_COLOR, corner_radius=0)
        self.border_frame.pack(fill="both", expand=True)

        # Fixed Header Frame
        self.header_frame = ctk.CTkFrame(self.border_frame, fg_color=GRID_LINE_COLOR, corner_radius=0, height=28)
        self.header_frame.pack(fill="x", side="top", padx=1, pady=(1, 0))
        self.header_frame.pack_propagate(False)
        
        # Scrollable Data Frame 
        self.scroll_frame = ctk.CTkScrollableFrame(self.border_frame, fg_color=GRID_LINE_COLOR, corner_radius=0)
        self.scroll_frame.pack(fill="both", expand=True, side="top", padx=1, pady=(0, 1))
        
        # Ensure inner canvas also matches the line color for seamless borders
        try:
            self.scroll_frame._parent_frame.configure(fg_color=GRID_LINE_COLOR)
        except AttributeError:
            pass
            
        self.header_labels = []
        self._draw_headers()

    def _draw_headers(self):
        for c, (header, w) in enumerate(zip(self.headers, self.col_widths)):
            # Distribute weights for responsive resizing
            weight = w if c < len(self.data_keys) else 0
            self.scroll_frame.grid_columnconfigure(c, weight=weight)
            
            lbl = ctk.CTkLabel(
                self.header_frame, text=header, height=28, font=("Arial", 12, "bold"),
                fg_color=HEADER_BG, text_color=HEADER_TEXT, corner_radius=0
            )
            # Padding (0, 1) creates the 1px right/bottom borders for headers
            lbl.pack(side="left", padx=(0, 1), pady=0, fill="y")
            self.header_labels.append(lbl)
            
        # Spacer that algorithmically stretches to cover the scrollbar width area
        self.spacer = ctk.CTkFrame(self.header_frame, fg_color=HEADER_BG, corner_radius=0, width=16)
        self.spacer.pack(side="left", fill="y", padx=0, pady=0)

    def _sync_alignment(self, event=None):
        """ Dynamically matches the header labels to the exact pixel width of the grid columns """
        if not self.rows: 
            return
            
        # 1. Sync header widths exactly to the first row's cell widths
        for c, key in enumerate(self.data_keys):
            actual_width = self.rows[0][key].winfo_width()
            if actual_width > 1:
                self.header_labels[c].configure(width=actual_width)
        
        # 2. Sync the delete button column width
        del_btn_width = self.rows[0]["_del_btn"].winfo_width()
        if del_btn_width > 1:
            self.header_labels[-1].configure(width=del_btn_width)
        
        # 3. Sync spacer exactly to the scrollbar width
        canvas_w = self.scroll_frame._parent_canvas.winfo_width()
        frame_w = self.scroll_frame._parent_frame.winfo_width()
        scrollbar_w = canvas_w - frame_w
        if scrollbar_w > 0:
            self.spacer.configure(width=scrollbar_w)

    def add_row(self, data_dict=None, is_new=False, is_imported=False):
        if data_dict is None:
            data_dict = {key: "" for key in self.data_keys}
            
        r = len(self.rows) + 1
        row_entries = {"_orig_vals": {}}
        
        if not is_new and not is_imported:
            row_entries["_orig_vals"] = {k: str(data_dict.get(k, "")) for k in self.data_keys}
            
        for c, key in enumerate(self.data_keys):
            var = ctk.StringVar(value=str(data_dict.get(key, "")))
            entry = ctk.CTkEntry(
                self.scroll_frame, height=26, 
                corner_radius=0, border_width=0, 
                fg_color=CELL_BG, text_color=CELL_TEXT,
                textvariable=var
            )
            # 1px line separation via padding right/bottom
            entry.grid(row=r, column=c, padx=(0, 1), pady=(0, 1), sticky="nsew")
            row_entries[key] = entry
            row_entries[f"_{key}_var"] = var
            
            def check_dirty(*args, widget=entry, k=key, sv=var, current_row=row_entries):
                origs = current_row["_orig_vals"]
                if k not in origs or sv.get() != origs[k]:
                    widget.configure(fg_color=DIRTY_COLOR)
                else:
                    widget.configure(fg_color=CELL_BG)
                    
            var.trace_add("write", check_dirty)
            check_dirty()
            
        del_btn = ctk.CTkButton(
            self.scroll_frame, text="🗑️", width=40, height=26, corner_radius=0, 
            fg_color="#3a3b46", hover_color="#ff4747",
            command=lambda: self.delete_row(row_entries)
        )
        # Flush to the right (padx=0) because the outer border provides the final line
        del_btn.grid(row=r, column=len(self.data_keys), padx=(0, 0), pady=(0, 1), sticky="nsew")
        row_entries["_del_btn"] = del_btn
        
        self.rows.append(row_entries)
        
        # ⚠️ add="+" IS CRITICAL: It binds our logic WITHOUT destroying the internal scrolling events
        if len(self.rows) == 1:
            for key in self.data_keys:
                row_entries[key].bind("<Configure>", self._sync_alignment, add="+")
            row_entries["_del_btn"].bind("<Configure>", self._sync_alignment, add="+")
            self.scroll_frame._parent_canvas.bind("<Configure>", self._sync_alignment, add="+")
            self.scroll_frame._parent_frame.bind("<Configure>", self._sync_alignment, add="+")
        
        if is_new:
            row_entries[self.data_keys[0]].focus_set()
            self.scroll_frame.after(50, lambda: self.scroll_frame._parent_canvas.yview_moveto(1.0))

    def delete_row(self, row_entries):
        for k in self.data_keys:
            row_entries[k].destroy()
        row_entries["_del_btn"].destroy()
        self.rows.remove(row_entries)
        self._repack_rows()

    def _repack_rows(self):
        for i, row in enumerate(self.rows, start=1):
            for c, key in enumerate(self.data_keys):
                row[key].grid(row=i, column=c, padx=(0, 1), pady=(0, 1), sticky="nsew")
            row["_del_btn"].grid(row=i, column=len(self.data_keys), padx=(0, 0), pady=(0, 1), sticky="nsew")
            
        # Safely rebind alignment to the new top row just in case
        if self.rows:
            for key in self.data_keys:
                self.rows[0][key].bind("<Configure>", self._sync_alignment, add="+")
            self.rows[0]["_del_btn"].bind("<Configure>", self._sync_alignment, add="+")

    def clear_rows(self):
        for row in self.rows:
            for k in self.data_keys:
                row[k].destroy()
            row["_del_btn"].destroy()
        self.rows.clear()

    def update_baseline(self):
        for row in self.rows:
            row["_orig_vals"] = {k: row[f"_{k}_var"].get() for k in self.data_keys}
            for key in self.data_keys:
                row[key].configure(fg_color=CELL_BG)

    def filter_rows(self, query):
        query = query.lower()
        visible_r = 1
        for row in self.rows:
            match = False
            for key in self.data_keys:
                if query in row[f"_{key}_var"].get().lower():
                    match = True
                    break
            
            if match:
                for c, key in enumerate(self.data_keys):
                    row[key].grid(row=visible_r, column=c, padx=(0, 1), pady=(0, 1), sticky="nsew")
                row["_del_btn"].grid(row=visible_r, column=len(self.data_keys), padx=(0, 0), pady=(0, 1), sticky="nsew")
                visible_r += 1
            else:
                for key in self.data_keys:
                    row[key].grid_remove()
                row["_del_btn"].grid_remove()


class PlcMasterApp(ctk.CTk):
    def __init__(self, config_file="modbus_mapping.json"):
        super().__init__()
        self.title("PLC MASTER")
        self.geometry("850x650")
        self.configure(fg_color=BG_COLOR)
        self.config_file = config_file
        self.data = self._load_data()
        self._build_ui()

    def _load_data(self):
        default = {
            "settings": {"PLC_IP": ""}, 
            "coils": {"meta": {"start_address": 0, "size": 0}, "data": {}}, 
            "registers": {}, "ips": {}
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    default.update(json.load(f))
            except Exception:
                pass
        return default

    def _build_ui(self):
        self.tabview = ctk.CTkTabview(
            self, fg_color=FRAME_COLOR, segmented_button_selected_color=ACCENT_COLOR,
            segmented_button_selected_hover_color=HOVER_COLOR, height=450
        )
        self.tabview.pack(fill="both", expand=True, padx=10, pady=5)

        self.tab_settings = self.tabview.add("Settings")
        self.tab_coils = self.tabview.add("Coils")
        self.tab_registers = self.tabview.add("Registers")
        self.tab_ips = self.tabview.add("IP Addresses")

        self._build_settings_tab()
        self._build_coils_tab()
        self._build_registers_tab()
        self._build_ips_tab()

        footer = ctk.CTkFrame(self, fg_color="transparent", height=40)
        footer.pack(fill="x", side="bottom", padx=10, pady=10)
        ctk.CTkButton(
            footer, text="Save Configuration", fg_color=ACCENT_COLOR, hover_color=HOVER_COLOR,
            height=30, command=self.save_config
        ).pack(side="right")

    def _bind_dirty_check(self, widget, string_var, initial_value):
        widget._baseline_val = str(initial_value)
        def check(*args):
            if string_var.get() != widget._baseline_val:
                widget.configure(fg_color=DIRTY_COLOR, text_color=CELL_TEXT)
            else:
                widget.configure(fg_color=["#F9F9FA", "#343638"], text_color=TEXT_COLOR)
        string_var.trace_add("write", check)
        check()

    def import_csv(self, grid_target):
        filepath = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if not filepath: return
            
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)
                grid_target.clear_rows()
                for row in reader:
                    if not row: continue
                    data_dict = {key: (row[i].strip() if i < len(row) else "") for i, key in enumerate(grid_target.data_keys)}
                    grid_target.add_row(data_dict, is_imported=True)
        except Exception as e:
            messagebox.showerror("Import Error", f"Failed to import CSV:\n{str(e)}")

    def export_csv(self, grid_target):
        filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if not filepath: return
        
        try:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(grid_target.headers[:-1])
                for row in grid_target.rows:
                    writer.writerow([row[f"_{k}_var"].get() for k in grid_target.data_keys])
            messagebox.showinfo("Success", "CSV exported successfully!")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export CSV:\n{str(e)}")

    def _create_toolbar(self, parent, grid_target):
        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.pack(fill="x", padx=5, pady=5)
        
        ctk.CTkButton(
            toolbar, text="+ Add Row", fg_color=ACCENT_COLOR, hover_color=HOVER_COLOR, 
            height=26, width=90, corner_radius=4, command=lambda: grid_target.add_row(is_new=True)
        ).pack(side="left")

        ctk.CTkButton(
            toolbar, text="Import CSV", fg_color="#43a047", hover_color="#2e7d32", 
            height=26, width=90, corner_radius=4, command=lambda: self.import_csv(grid_target)
        ).pack(side="left", padx=(10, 5))

        ctk.CTkButton(
            toolbar, text="Export CSV", fg_color="#0288d1", hover_color="#0277bd", 
            height=26, width=90, corner_radius=4, command=lambda: self.export_csv(grid_target)
        ).pack(side="left", padx=5)
        
        search_var = ctk.StringVar()
        search_var.trace_add("write", lambda *args: grid_target.filter_rows(search_var.get()))
        
        ctk.CTkEntry(
            toolbar, width=200, height=26, placeholder_text="Enter text...", 
            textvariable=search_var, corner_radius=4
        ).pack(side="right")
        
        ctk.CTkLabel(toolbar, text="Search:").pack(side="right", padx=5)

    def _build_settings_tab(self):
        frame = ctk.CTkFrame(self.tab_settings, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        meta = self.data.get("coils", {}).get("meta", {})
        
        row1 = ctk.CTkFrame(frame, fg_color="transparent")
        row1.pack(fill="x", pady=10)
        ctk.CTkLabel(row1, text="PLC IP Address:", width=150, anchor="w").pack(side="left")
        self.var_plc_ip = ctk.StringVar(value=self.data.get("settings", {}).get("PLC_IP", ""))
        self.ui_plc_ip = ctk.CTkEntry(row1, width=250, height=28, textvariable=self.var_plc_ip)
        self.ui_plc_ip.pack(side="left", padx=5)
        self._bind_dirty_check(self.ui_plc_ip, self.var_plc_ip, self.var_plc_ip.get())

        row2 = ctk.CTkFrame(frame, fg_color="transparent")
        row2.pack(fill="x", pady=10)
        ctk.CTkLabel(row2, text="Coils Start Address:", width=150, anchor="w").pack(side="left")
        self.var_coils_start = ctk.StringVar(value=str(meta.get("start_address", 0)))
        self.ui_coils_start = ctk.CTkEntry(row2, width=250, height=28, textvariable=self.var_coils_start)
        self.ui_coils_start.pack(side="left", padx=5)
        self._bind_dirty_check(self.ui_coils_start, self.var_coils_start, self.var_coils_start.get())
        
        row3 = ctk.CTkFrame(frame, fg_color="transparent")
        row3.pack(fill="x", pady=10)
        ctk.CTkLabel(row3, text="Coils Size:", width=150, anchor="w").pack(side="left")
        self.var_coils_size = ctk.StringVar(value=str(meta.get("size", 0)))
        self.ui_coils_size = ctk.CTkEntry(row3, width=250, height=28, textvariable=self.var_coils_size)
        self.ui_coils_size.pack(side="left", padx=5)
        self._bind_dirty_check(self.ui_coils_size, self.var_coils_size, self.var_coils_size.get())

    def _build_coils_tab(self):
        self.grid_coils = SpreadsheetGrid(
            self.tab_coils, headers=["Coil Name", "Address", ""], 
            col_widths=[300, 150, 40], data_keys=["name", "address"]
        )
        self._create_toolbar(self.tab_coils, self.grid_coils)
        self.grid_coils.pack(fill="both", expand=True, padx=5, pady=5)
        
        for k, v in self.data.get("coils", {}).get("data", {}).items():
            self.grid_coils.add_row({"name": k, "address": v})

    def _build_registers_tab(self):
        self.grid_regs = SpreadsheetGrid(
            self.tab_registers, headers=["Register Code", "Start Address", "Size", ""], 
            col_widths=[250, 100, 100, 40], data_keys=["code", "start", "size"]
        )
        self._create_toolbar(self.tab_registers, self.grid_regs)
        self.grid_regs.pack(fill="both", expand=True, padx=5, pady=5)
        
        for k, v in self.data.get("registers", {}).items():
            self.grid_regs.add_row({"code": k, "start": v.get("start_address", ""), "size": v.get("size", "")})

    def _build_ips_tab(self):
        self.grid_ips = SpreadsheetGrid(
            self.tab_ips, headers=["Group", "Device Name", "URL / IP", ""], 
            col_widths=[100, 200, 250, 40], data_keys=["group", "name", "url"]
        )
        self._create_toolbar(self.tab_ips, self.grid_ips)
        self.grid_ips.pack(fill="both", expand=True, padx=5, pady=5)
        
        for group, devices in self.data.get("ips", {}).items():
            for name, url in devices.items():
                self.grid_ips.add_row({"group": group, "name": name, "url": url})

    def _validate_and_clean_grid(self, grid, tab_name):
        rows_to_delete = []
        for row in grid.rows:
            values = [row[f"_{k}_var"].get().strip() for k in grid.data_keys]
            filled_count = sum(bool(v) for v in values)
            
            if filled_count == 0:
                rows_to_delete.append(row)
            elif filled_count < len(grid.data_keys):
                messagebox.showerror(
                    "Validation Error", 
                    f"Cannot save partially filled rows in '{tab_name}'.\nPlease complete all fields or delete the row."
                )
                return False
                
        for row in rows_to_delete:
            grid.delete_row(row)
            
        return True

    def save_config(self):
        if not self._validate_and_clean_grid(self.grid_coils, "Coils"): return
        if not self._validate_and_clean_grid(self.grid_regs, "Registers"): return
        if not self._validate_and_clean_grid(self.grid_ips, "IP Addresses"): return

        if not messagebox.askyesno("Confirm Save", "Are you sure you want to save these changes?"):
            return
            
        try:
            new_data = {
                "settings": {"PLC_IP": self.ui_plc_ip.get().strip()},
                "coils": {
                    "meta": {
                        "start_address": int(self.ui_coils_start.get()),
                        "size": int(self.ui_coils_size.get())
                    },
                    "data": {}
                },
                "registers": {},
                "ips": {}
            }
            
            for row in self.grid_coils.rows:
                new_data["coils"]["data"][row["_name_var"].get().strip()] = int(row["_address_var"].get().strip())
                    
            for row in self.grid_regs.rows:
                new_data["registers"][row["_code_var"].get().strip()] = {
                    "start_address": int(row["_start_var"].get()), 
                    "size": int(row["_size_var"].get())
                }
                    
            for row in self.grid_ips.rows:
                g = row["_group_var"].get().strip()
                n = row["_name_var"].get().strip()
                u = row["_url_var"].get().strip()
                new_data["ips"].setdefault(g, {})[n] = u

            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(new_data, f, indent=2)
                
            self.grid_coils.update_baseline()
            self.grid_regs.update_baseline()
            self.grid_ips.update_baseline()
            
            self.ui_plc_ip._baseline_val = self.var_plc_ip.get()
            self.ui_coils_start._baseline_val = self.var_coils_start.get()
            self.ui_coils_size._baseline_val = self.var_coils_size.get()
            
            self.ui_plc_ip.configure(fg_color=["#F9F9FA", "#343638"], text_color=TEXT_COLOR)
            self.ui_coils_start.configure(fg_color=["#F9F9FA", "#343638"], text_color=TEXT_COLOR)
            self.ui_coils_size.configure(fg_color=["#F9F9FA", "#343638"], text_color=TEXT_COLOR)
            
            messagebox.showinfo("Success", "Configuration saved successfully!")
            
        except ValueError:
            messagebox.showerror("Validation Error", "Ensure all numerical fields contain valid integers.")


if __name__ == "__main__":
    app = PlcMasterApp()
    app.mainloop()