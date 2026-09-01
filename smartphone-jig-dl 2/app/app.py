import ctypes
import logging

# Garante que o Tkinter e a API do Windows usem os pixels reais do monitor,
# corrigindo desalinhamentos se o Windows estiver com zoom de 125%, 150%, etc.
# Como o servidor/automação agora rodam nesse mesmo processo (não mais em um
# main.exe filho separado), isso também garante que os cliques do PyAutoGUI
# usem coordenadas físicas, não virtualizadas por DPI.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# Configurado aqui (em vez de um StreamHandler fixo em sys.stdout/stderr,
# que é None num EXE windowed sem console) para que logging.info/error (do
# uvicorn, do FastAPI e da automação) tenham um handler para propagar até
# -- o handler real que exibe as linhas no console da UI é anexado/removido
# pelo ServerSupervisor a cada start/stop do servidor.
logging.getLogger().setLevel(logging.INFO)

from ui.app_window import SetupApp

if __name__ == "__main__":
    SetupApp().mainloop()