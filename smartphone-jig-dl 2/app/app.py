import ctypes
import os
import sys

# Garante que o Tkinter e a API do Windows usem os pixels reais do monitor,
# corrigindo desalinhamentos se o Windows estiver com zoom de 125%, 150%, etc.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from ui.app_window import SetupApp

if __name__ == "__main__":
    # base_dir é onde main.py/main.exe (o processo supervisionado) deve ser
    # procurado: a pasta do executável quando compilado, ou a pasta deste
    # próprio arquivo em desenvolvimento -- nunca o diretório de trabalho
    # atual, que pode ser outro dependendo de como o app foi lançado.
    base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
        else os.path.dirname(os.path.abspath(__file__))
    SetupApp(base_dir).mainloop()