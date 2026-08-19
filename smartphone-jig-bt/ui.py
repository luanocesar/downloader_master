import json
import os
import tkinter as tk
from tkinter import messagebox, ttk


class SetupApp(tk.Tk):

    def __init__(self, config_filename="config.json"):
        super().__init__()
        self.title("Setup - Configuration Manager")
        self.geometry("920x580")
        self.config_filename = config_filename

        self.robot_rows = []
        self.coord_rows = []
        self._cached_coords = []

        self._init_ui()
        self.load_config()

    def _init_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        # Tab 1: Robots
        self.tab_robots = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_robots, text="Robots")
        self._setup_robots_tab()

        # Tab 2: PyAutoGUI Coordinates
        self.tab_coords = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_coords, text="PyAutoGUI Coordinates")
        self._setup_coords_tab()

        # Rodapé
        footer = ttk.Frame(self)
        footer.pack(fill="x", side="bottom", padx=10, pady=10)

        ttk.Button(
            footer, text="Save Configuration", command=self.save_config
        ).pack(side="right", padx=5)
        ttk.Button(footer, text="Reload", command=self.load_config).pack(
            side="right"
        )

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)

    # --- TAB 1: ROBOTS ---
    def _setup_robots_tab(self):
        toolbar = ttk.Frame(self.tab_robots)
        toolbar.pack(fill="x", padx=10, pady=5)

        ttk.Button(
            toolbar, text="+ Add Robot", command=self.add_robot_row
        ).pack(side="left")

        container = ttk.Frame(self.tab_robots)
        container.pack(fill="both", expand=True, padx=10, pady=5)

        self.canvas_robots = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            container, orient="vertical", command=self.canvas_robots.yview
        )
        self.scrollable_robots = ttk.Frame(self.canvas_robots)

        self.scrollable_robots.bind(
            "<Configure>",
            lambda e: self.canvas_robots.configure(
                scrollregion=self.canvas_robots.bbox("all")
            ),
        )
        self.canvas_robots.create_window(
            (0, 0), window=self.scrollable_robots, anchor="nw"
        )
        self.canvas_robots.configure(yscrollcommand=scrollbar.set)

        self.canvas_robots.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        headers = ["Enabled", "Robot Name", "IP Address", "CLP Address", ""]
        widths = [8, 25, 20, 20, 8]
        for col, (h, w) in enumerate(zip(headers, widths)):
            lbl = ttk.Label(
                self.scrollable_robots, text=h, font=("Segoe UI", 9, "bold")
            )
            lbl.grid(row=0, column=col, padx=5, pady=5, sticky="w")

    def add_robot_row(self, name="", ip="", clp_address="", enabled=True):
        row_idx = len(self.robot_rows) + 1

        var_enabled = tk.BooleanVar(value=enabled)
        chk = ttk.Checkbutton(self.scrollable_robots, variable=var_enabled)
        chk.grid(row=row_idx, column=0, padx=5, pady=2)

        entry_name = ttk.Entry(self.scrollable_robots, width=25)
        entry_name.insert(0, name)
        entry_name.grid(row=row_idx, column=1, padx=5, pady=2)

        entry_ip = ttk.Entry(self.scrollable_robots, width=20)
        entry_ip.insert(0, ip)
        entry_ip.grid(row=row_idx, column=2, padx=5, pady=2)

        entry_clp = ttk.Entry(self.scrollable_robots, width=20)
        entry_clp.insert(0, clp_address)
        entry_clp.grid(row=row_idx, column=3, padx=5, pady=2)

        row_widgets = {
            "enabled": var_enabled,
            "name": entry_name,
            "ip": entry_ip,
            "clp": entry_clp,
        }

        btn_del = ttk.Button(
            self.scrollable_robots,
            text="X",
            width=3,
            command=lambda rw=row_widgets: self._delete_robot_row(rw),
        )
        btn_del.grid(row=row_idx, column=4, padx=5, pady=2)

        row_widgets["delete_btn"] = btn_del
        row_widgets["check_btn"] = chk
        self.robot_rows.append(row_widgets)

    def _delete_robot_row(self, row_dict):
        for widget_key in ["check_btn", "name", "ip", "clp", "delete_btn"]:
            row_dict[widget_key].destroy()
        self.robot_rows.remove(row_dict)

    # --- TAB 2: COORDINATES ---
    def _setup_coords_tab(self):
        container = ttk.Frame(self.tab_coords)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        self.canvas_coords = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            container, orient="vertical", command=self.canvas_coords.yview
        )
        self.scrollable_coords = ttk.Frame(self.canvas_coords)

        self.scrollable_coords.bind(
            "<Configure>",
            lambda e: self.canvas_coords.configure(
                scrollregion=self.canvas_coords.bbox("all")
            ),
        )
        self.canvas_coords.create_window(
            (0, 0), window=self.scrollable_coords, anchor="nw"
        )
        self.canvas_coords.configure(yscrollcommand=scrollbar.set)

        self.canvas_coords.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _sync_coords_tab(self):
        for widget in self.scrollable_coords.winfo_children():
            widget.destroy()

        headers = ["Active", "Robot Link", "X Coordinate", "Y Coordinate", "Capturar Posição"]
        for col, h in enumerate(headers):
            ttk.Label(
                self.scrollable_coords, text=h, font=("Segoe UI", 9, "bold")
            ).grid(row=0, column=col, padx=10, pady=5, sticky="w")

        existing_coords = {
            r["robot_name"]: r for r in getattr(self, "_cached_coords", [])
        }
        self.coord_rows = []

        current_robots = [
            r["name"].get().strip()
            for r in self.robot_rows
            if r["name"].get().strip()
        ]

        for idx, robot_name in enumerate(current_robots, start=1):
            coord_info = existing_coords.get(
                robot_name, {"x": "0", "y": "0", "enabled": True}
            )

            var_enabled = tk.BooleanVar(value=coord_info.get("enabled", True))
            chk = ttk.Checkbutton(self.scrollable_coords, variable=var_enabled)
            chk.grid(row=idx, column=0, padx=10, pady=2)

            lbl_name = ttk.Label(
                self.scrollable_coords, text=robot_name, width=25
            )
            lbl_name.grid(row=idx, column=1, padx=10, pady=2, sticky="w")

            # Entry X
            entry_x = ttk.Entry(self.scrollable_coords, width=12)
            entry_x.insert(0, str(coord_info.get("x", 0)))
            entry_x.grid(row=idx, column=2, padx=10, pady=2)

            # Entry Y
            entry_y = ttk.Entry(self.scrollable_coords, width=12)
            entry_y.insert(0, str(coord_info.get("y", 0)))
            entry_y.grid(row=idx, column=3, padx=10, pady=2)

            # Botão Único de Captura
            btn_pick_both = ttk.Button(
                self.scrollable_coords,
                text="🎯 Capturar (X, Y)",
                command=lambda ex=entry_x, ey=entry_y: self._start_capture_overlay(ex, ey),
            )
            btn_pick_both.grid(row=idx, column=4, padx=10, pady=2)

            self.coord_rows.append(
                {
                    "robot_name": robot_name,
                    "enabled": var_enabled,
                    "x": entry_x,
                    "y": entry_y,
                }
            )

    def _start_capture_overlay(self, entry_x, entry_y):
        """Cria uma tela cheia transparente para capturar o clique do mouse."""
        overlay = tk.Toplevel(self)
        overlay.attributes("-fullscreen", True)
        overlay.attributes("-alpha", 0.3)  # Nível de transparência (30%)
        overlay.attributes("-topmost", True)
        overlay.config(bg="black", cursor="crosshair")

        def on_mouse_move(event):
            # Atualiza os campos em tempo real para feedback visual
            entry_x.delete(0, tk.END)
            entry_x.insert(0, str(event.x_root))
            entry_y.delete(0, tk.END)
            entry_y.insert(0, str(event.y_root))

        def on_mouse_click(event):
            # Trava as coordenadas no clique e fecha o overlay
            entry_x.delete(0, tk.END)
            entry_x.insert(0, str(event.x_root))
            entry_y.delete(0, tk.END)
            entry_y.insert(0, str(event.y_root))
            overlay.destroy()

        def on_escape(event):
            # Cancela a captura se pressionar ESC
            overlay.destroy()

        # Bind dos eventos
        overlay.bind("<Motion>", on_mouse_move)
        overlay.bind("<Button-1>", on_mouse_click)
        overlay.bind("<Escape>", on_escape)

    def _on_tab_change(self, event):
        if self.notebook.select() == self.tab_coords._w:
            self._cache_current_coords()
            self._sync_coords_tab()

    def _cache_current_coords(self):
        if self.coord_rows:
            self._cached_coords = [
                {
                    "robot_name": row["robot_name"],
                    "x": row["x"].get(),
                    "y": row["y"].get(),
                    "enabled": row["enabled"].get(),
                }
                for row in self.coord_rows
            ]

    # --- JSON STORAGE ---
    def save_config(self):
        self._cache_current_coords()

        robots_payload = [
            {
                "enabled": r["enabled"].get(),
                "name": r["name"].get().strip(),
                "ip": r["ip"].get().strip(),
                "clp_address": r["clp"].get().strip(),
            }
            for r in self.robot_rows
            if r["name"].get().strip()
        ]

        payload = {
            "robots": robots_payload,
            "coordinates": getattr(self, "_cached_coords", []),
        }

        with open(self.config_filename, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)

        messagebox.showinfo("Success", "Configuration saved successfully!")

    def load_config(self):
        for row in list(self.robot_rows):
            self._delete_robot_row(row)

        if not os.path.exists(self.config_filename):
            self.add_robot_row("Robot_1", "192.168.1.10", "%MW100", True)
            return

        with open(self.config_filename, "r", encoding="utf-8") as f:
            data = json.load(f)

        for r in data.get("robots", []):
            self.add_robot_row(
                name=r.get("name", ""),
                ip=r.get("ip", ""),
                clp_address=r.get("clp_address", ""),
                enabled=r.get("enabled", True),
            )

        self._cached_coords = data.get("coordinates", [])


if __name__ == "__main__":
    app = SetupApp()
    app.mainloop()