import ctypes
import tkinter as tk
from ctypes import wintypes

from pywinauto import Desktop

VK_LBUTTON = 0x01
VK_ESCAPE = 0x1B

# Chrome de janelas do próprio Windows que nunca é um alvo de automação válido.
OS_CHROME_TITLES = ["Program Manager", "Taskbar", "Windows Shell Experience Host"]


def pick_window_title(tk_widget, own_window_title, on_hover, on_confirmed, on_cancelled):
    """Inicia um picker de janela: o operador passa o mouse sobre qualquer
    janela (cada janela válida sob o cursor dispara `on_hover(title)`, para
    atualização ao vivo) e clica para confirmar (`on_confirmed()`) — ESC
    cancela (`on_cancelled()`) sem reverter o que já foi escrito por
    `on_hover`, replicando o comportamento original. `tk_widget` só precisa
    fornecer `.after()` (normalmente o próprio Tk root) para o polling.
    """
    user32 = ctypes.windll.user32
    invalid_titles = [own_window_title, *OS_CHROME_TITLES]

    def _wait_for_release():
        if user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000:
            tk_widget.after(50, _wait_for_release)
        else:
            tk_widget.after(50, _poll)

    def _poll():
        if user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000:
            on_cancelled()
            return

        if user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000:
            on_confirmed()
            return

        title = _title_under_cursor(invalid_titles)
        if title:
            on_hover(title)

        tk_widget.after(50, _poll)

    _wait_for_release()


def _title_under_cursor(invalid_titles):
    user32 = ctypes.windll.user32

    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    hwnd = user32.WindowFromPoint(pt)

    if not hwnd:
        return None

    root_hwnd = user32.GetAncestor(hwnd, 2)
    length = user32.GetWindowTextLengthW(root_hwnd)
    if length <= 0:
        return None

    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(root_hwnd, buff, length + 1)
    title = buff.value.strip()

    if title and title not in invalid_titles:
        return title
    return None


def capture_click_coordinates(tk_root, target_window_title, on_captured, on_error):
    """Abre um overlay transparente em tela cheia; o próximo clique do
    operador vira uma coordenada relativa à janela `target_window_title`
    (ESC cancela sem chamar `on_captured`). `on_error(title, message)` é
    chamado se a janela alvo não puder ser localizada/conectada."""
    try:
        janela = Desktop(backend="uia").window(title=target_window_title)

        if not janela.exists():
            on_error("Erro", f"Janela '{target_window_title}' não foi encontrada.\nAbra o aplicativo alvo antes de capturar.")
            return

        if janela.is_minimized():
            janela.restore()

        janela.set_focus()

        rect = janela.rectangle()
        janela_left = rect.left
        janela_top = rect.top

    except Exception as e:
        on_error("Erro de Conexão", f"Falha ao conectar com a janela '{target_window_title}':\n\n{str(e)}")
        return

    overlay = tk.Toplevel(tk_root)
    overlay.attributes("-fullscreen", True)
    overlay.attributes("-alpha", 0.01)
    overlay.attributes("-topmost", True)
    overlay.config(cursor="crosshair")

    def on_mouse_click(event):
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))

        rel_x = pt.x - janela_left
        rel_y = pt.y - janela_top

        overlay.destroy()
        on_captured(rel_x, rel_y)

    def on_escape(event):
        overlay.destroy()

    overlay.bind("<Button-1>", on_mouse_click)
    overlay.bind("<Escape>", on_escape)
