import sys
import logging
import json
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from pywinauto import Desktop
import time
import pyautogui
import uvicorn

# Impede que o script quebre se o operador mover o mouse sem querer
pyautogui.FAILSAFE = False

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
app = FastAPI()

class LabelCodeRequest(BaseModel):
    mapped_labels: dict[str, str]

VALID_ACTION_TYPES = {"none", "click", "type_text", "key_press"}
VALID_KEYS = {"enter", "tab", "space", "backspace"}

# --- INÍCIO: CARREGAMENTO E VALIDAÇÃO ESTrita DO CONFIG.JSON ---
CONFIG_FILE = "config.json"

try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config_data = json.load(f)
except FileNotFoundError:
    logging.error(f"-> FATAL ERROR: Arquivo de configuração '{CONFIG_FILE}' não encontrado.")
    logging.error("-> Crie o arquivo baseado no modelo padrão (config.template.json).")
    sys.exit(1)
except json.JSONDecodeError as e:
    logging.error(f"-> FATAL ERROR: Formato JSON inválido no '{CONFIG_FILE}': {e}")
    sys.exit(1)

# Validação de Tipagem e Estrutura
try:
    _ThisServerHostIP = config_data["SERVER_HOST_IP"]
    _ThisServerPort = config_data["SERVER_PORT"]
    _TargetWindowForAutomatedInput = config_data["TARGET_WINDOW_TITLE"]
    SLOTS = config_data["SLOTS"]

    # Checagem de Tipos
    if not isinstance(_ThisServerHostIP, str):
        raise ValueError("'SERVER_HOST_IP' deve ser do tipo <string>")
    if not isinstance(_ThisServerPort, int):
        raise ValueError("'SERVER_PORT' deve ser do tipo <integer>")
    if not isinstance(_TargetWindowForAutomatedInput, str):
        raise ValueError("'TARGET_WINDOW_TITLE' deve ser do tipo <string>")
    if not isinstance(SLOTS, dict):
        raise ValueError("'SLOTS' deve ser um objeto JSON")

    # Checagem profunda de cada Slot (enabled, actions [...])
    for slot_key, slot in SLOTS.items():
        if not isinstance(slot, dict):
            raise ValueError(f"'SLOTS'['{slot_key}'] deve ser um objeto JSON")

        enabled = slot.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"'SLOTS'['{slot_key}']['enabled'] deve ser <boolean>")

        actions = slot.get("actions", [])
        if not isinstance(actions, list):
            raise ValueError(f"'SLOTS'['{slot_key}']['actions'] deve ser uma lista")

        for i, action in enumerate(actions):
            if not isinstance(action, dict):
                raise ValueError(f"'SLOTS'['{slot_key}']['actions'][{i}] deve ser um objeto JSON")

            a_type = action.get("type", "none")
            if a_type not in VALID_ACTION_TYPES:
                raise ValueError(f"'SLOTS'['{slot_key}']['actions'][{i}]['type'] inválido: '{a_type}'")

            if a_type == "click":
                x, y = action.get("x"), action.get("y")
                if not isinstance(x, int) or not isinstance(y, int):
                    raise ValueError(f"'SLOTS'['{slot_key}']['actions'][{i}] do tipo 'click' precisa de 'x' e 'y' <integer>")

            if a_type == "key_press" and action.get("key", "enter") not in VALID_KEYS:
                raise ValueError(f"'SLOTS'['{slot_key}']['actions'][{i}]['key'] inválido: '{action.get('key')}'")

    logging.info(f"-> Configurações carregadas e validadas com sucesso de {CONFIG_FILE}.")

except KeyError as e:
    logging.error(f"-> FATAL ERROR: Chave obrigatória ausente no {CONFIG_FILE}: {e}")
    sys.exit(1)
except ValueError as e:
    logging.error(f"-> FATAL ERROR: Erro de validação de valor no {CONFIG_FILE}: {e}")
    sys.exit(1)
# --- FIM: CARREGAMENTO E VALIDAÇÃO ESTRITA ---

ROBO_OCUPADO = False

def _executar_acoes_do_slot(slot_key, slot, label_code, janela_left, janela_top):
    for action in slot.get("actions", []):
        if not action.get("enabled", True):
            continue

        a_type = action.get("type", "none")

        if a_type == "click":
            clique_x = janela_left + action.get("x", 0)
            clique_y = janela_top + action.get("y", 0)
            logging.info(f"-> Mapeando Slot {slot_key}: Clicando no alvo (X:{clique_x}, Y:{clique_y})")
            pyautogui.click(clique_x, clique_y)
            time.sleep(0.15)

        elif a_type == "type_text":
            text = label_code if action.get("source", "barcode") == "barcode" else action.get("text", "")
            logging.info(f"   [DIGITANDO SLOT {slot_key}] -> '{text}'")
            pyautogui.write(text, interval=0.02)

        elif a_type == "key_press":
            key = action.get("key", "enter")
            pyautogui.press(key)
            time.sleep(0.15)

        # a_type == "none": nenhuma operação

def rotina_de_digitacao_fisica(labels_para_digitar):
    global ROBO_OCUPADO

    try:
        janela = Desktop(backend="uia").window(title=_TargetWindowForAutomatedInput)
        if janela.is_minimized():
            logging.info("-> Janela minimizada detectada! Restaurando posição original...")
            janela.restore()
            janela.maximize()
        janela.set_focus()

        time.sleep(0.5)
        rect = janela.rectangle()
        janela_left = rect.left
        janela_top = rect.top

        for slot_key, label_code in labels_para_digitar:
            slot = SLOTS[slot_key]
            _executar_acoes_do_slot(slot_key, slot, label_code, janela_left, janela_top)

    except Exception as e:
        logging.error(f"-> ERRO DURANTE DIGITAÇÃO: {e}")

    finally:
        ROBO_OCUPADO = False
        logging.info("=" * 50)
        logging.info("-> DIGITAÇÃO CONCLUÍDA. Robô livre para o próximo Jig.\n")

@app.post("/trigger")
def trigger(request: LabelCodeRequest, background_tasks: BackgroundTasks):
    global ROBO_OCUPADO

    logging.info("\n" + "=" * 50)
    logging.info(">>> NOVO GATILHO RECEBIDO <<<")

    if ROBO_OCUPADO:
        logging.warning("-> ALERTA: Robô já está trabalhando! Ignorando pulso duplicado do CLP.")
        return {"status": "busy", "message": "Robô ocupado, ignorando duplicata."}

    labels_para_digitar = []
    for slot_key in sorted(SLOTS.keys(), key=lambda k: int(k) if k.isdigit() else k):
        if not SLOTS[slot_key].get("enabled", True):
            continue
        label_code = request.mapped_labels.get(slot_key, "")
        if label_code:
            labels_para_digitar.append((slot_key, label_code))

    if not labels_para_digitar:
        logging.info("-> Todos os campos vazios ou Slots desabilitados. Abortando.")
        return {"status": "empty"}

    ROBO_OCUPADO = True

    logging.info("-> Pacote aceito. Liberando o Master e iniciando digitação em background...")
    background_tasks.add_task(rotina_de_digitacao_fisica, labels_para_digitar)

    return {"status": "success", "message": "Iniciando digitação física na tela."}

if __name__ == "__main__":
    logging.info("=" * 50)
    logging.info(f" SERVIDOR ENDPOINT INICIADO EM {_ThisServerHostIP}:{_ThisServerPort} - Aguardando ordens...")
    logging.info("=" * 50)
    uvicorn.run(app, host=_ThisServerHostIP, port=_ThisServerPort, log_config=None)
