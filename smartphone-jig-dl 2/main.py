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

CONFIG_FILE = "config.json"

def _load_and_validate_config(path):
    """Lê e valida config.json. Levanta FileNotFoundError, json.JSONDecodeError,
    KeyError ou ValueError em caso de problema; nunca chama sys.exit (quem
    chama decide se é fatal ou não)."""
    with open(path, "r", encoding="utf-8") as f:
        config_data = json.load(f)

    host = config_data["SERVER_HOST_IP"]
    port = config_data["SERVER_PORT"]
    target_window = config_data["TARGET_WINDOW_TITLE"]
    slots = config_data["SLOTS"]

    if not isinstance(host, str):
        raise ValueError("'SERVER_HOST_IP' deve ser do tipo <string>")
    if not isinstance(port, int):
        raise ValueError("'SERVER_PORT' deve ser do tipo <integer>")
    if not isinstance(target_window, str):
        raise ValueError("'TARGET_WINDOW_TITLE' deve ser do tipo <string>")
    if not isinstance(slots, dict):
        raise ValueError("'SLOTS' deve ser um objeto JSON")

    # Checagem profunda de cada Slot (enabled, actions [...])
    for slot_key, slot in slots.items():
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

    return host, port, target_window, slots

# --- INÍCIO: CARREGAMENTO E VALIDAÇÃO ESTRITA DO CONFIG.JSON (na inicialização) ---
try:
    _ThisServerHostIP, _ThisServerPort, _TargetWindowForAutomatedInput, SLOTS = _load_and_validate_config(CONFIG_FILE)
    logging.info(f"-> Configurações carregadas e validadas com sucesso de {CONFIG_FILE}.")
except FileNotFoundError:
    logging.error(f"-> FATAL ERROR: Arquivo de configuração '{CONFIG_FILE}' não encontrado.")
    logging.error("-> Crie o arquivo baseado no modelo padrão (config.template.json).")
    sys.exit(1)
except json.JSONDecodeError as e:
    logging.error(f"-> FATAL ERROR: Formato JSON inválido no '{CONFIG_FILE}': {e}")
    sys.exit(1)
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
            logging.info("-> Janela minimizada detectada! Restaurando...")
            janela.restore()

        # Sempre traz a janela para primeiro plano/foco antes de cada
        # automação, mesmo que não esteja minimizada: o operador pode ter
        # clicado em outra janela, ou outro programa pode ter sobreposto o
        # alvo entre um gatilho e o próximo. Sem isso, os cliques calculados
        # abaixo podem acabar acertando a janela errada.
        janela.set_focus()

        time.sleep(0.5)
        rect = janela.rectangle()
        janela_left = rect.left
        janela_top = rect.top

        for slot_key, label_code in labels_para_digitar:
            slot = SLOTS.get(slot_key)
            if slot is None:
                # A configuração pode ter sido salva/recarregada entre o
                # recebimento do POST e a execução em background; se o Slot
                # sumiu nesse meio-tempo, pula em vez de derrubar o lote todo.
                logging.warning(f"-> Slot {slot_key} não existe mais na configuração atual. Pulando.")
                continue

            try:
                _executar_acoes_do_slot(slot_key, slot, label_code, janela_left, janela_top)
            except Exception as e:
                # Isola a falha de UM Slot para não abortar os demais do lote.
                logging.error(f"-> ERRO ao executar ações do Slot {slot_key}: {e}. Pulando para o próximo Slot.")
                continue

    except Exception as e:
        logging.error(f"-> ERRO DURANTE DIGITAÇÃO: {e}")

    finally:
        ROBO_OCUPADO = False
        logging.info("=" * 50)
        logging.info("-> DIGITAÇÃO CONCLUÍDA. Robô livre para o próximo Jig.\n")

@app.post("/trigger")
def trigger(request: LabelCodeRequest, background_tasks: BackgroundTasks):
    global ROBO_OCUPADO, SLOTS, _TargetWindowForAutomatedInput

    logging.info("\n" + "=" * 50)
    logging.info(">>> NOVO GATILHO RECEBIDO <<<")

    if ROBO_OCUPADO:
        logging.warning("-> ALERTA: Robô já está trabalhando! Ignorando pulso duplicado do CLP.")
        return {"status": "busy", "message": "Robô ocupado, ignorando duplicata."}

    # Recarrega o config.json a cada gatilho, para que Slots/Actions
    # adicionados ou editados na UI depois que o servidor já estava rodando
    # sejam respeitados sem precisar reiniciar o processo. HOST/PORT não são
    # recarregados aqui pois o servidor já está vinculado a eles.
    try:
        _, _, reloaded_target_window, reloaded_slots = _load_and_validate_config(CONFIG_FILE)
        SLOTS = reloaded_slots
        _TargetWindowForAutomatedInput = reloaded_target_window
    except Exception as e:
        logging.warning(f"-> Falha ao recarregar {CONFIG_FILE} ({e}). Usando a última configuração válida em memória.")

    # Tolerante a posições em falta/fora de ordem: cada posição do POST só é
    # usada se existir em SLOTS, sempre amarrada pelo número (chave), nunca
    # pela ordem/posição no payload.
    labels_para_digitar = []
    unknown_keys = []
    for raw_key, label_code in request.mapped_labels.items():
        slot_key = raw_key.strip()

        if not label_code:
            continue
        if slot_key not in SLOTS:
            unknown_keys.append(raw_key)
            continue
        if not SLOTS[slot_key].get("enabled", True):
            continue

        labels_para_digitar.append((slot_key, label_code))

    # Ordem de execução determinística (1, 2, 3, ...), independente da ordem
    # em que as chaves chegaram no JSON do POST.
    labels_para_digitar.sort(key=lambda pair: int(pair[0]) if pair[0].isdigit() else pair[0])

    if unknown_keys:
        logging.warning(f"-> POST continha posições sem Slot correspondente na configuração atual (ignoradas): {unknown_keys}")

    if not labels_para_digitar:
        logging.info("-> Todos os campos vazios, Slots desabilitados ou sem correspondência. Abortando.")
        return {"status": "empty"}

    ROBO_OCUPADO = True

    logging.info(f"-> Pacote aceito para Slots {[k for k, _ in labels_para_digitar]}. Liberando o Master e iniciando digitação em background...")
    background_tasks.add_task(rotina_de_digitacao_fisica, labels_para_digitar)

    return {"status": "success", "message": "Iniciando digitação física na tela."}

if __name__ == "__main__":
    logging.info("=" * 50)
    logging.info(f" SERVIDOR ENDPOINT INICIADO EM {_ThisServerHostIP}:{_ThisServerPort} - Aguardando ordens...")
    logging.info("=" * 50)
    uvicorn.run(app, host=_ThisServerHostIP, port=_ThisServerPort, log_config=None)
