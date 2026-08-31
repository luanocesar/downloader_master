import re
import tkinter as tk
from tkinter import ttk

# Estilo compartilhado pelas tabelas Excel-like das 3 abas.
GRID_LINE = "#b0b0b0"
HEADER_BG = "#e8e8e8"
ROW_BG = "#ffffff"
HEADER_FONT = ("Segoe UI", 9, "bold")
CELL_FONT = ("Segoe UI", 9)
DANGER_BG = "#e57373"


def validate_integer_input(proposed):
    if proposed in ("", "-"):
        return True
    return bool(re.fullmatch(r"-?\d+", proposed))


def safe_int(value, default=0):
    value = (value or "").strip()
    if value in ("", "-"):
        return default
    try:
        return int(value)
    except ValueError:
        return default


def make_scrollable(parent):
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
