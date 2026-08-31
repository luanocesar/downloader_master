import json
import logging
import sys
from dataclasses import dataclass

VALID_ACTION_TYPES = {"none", "click", "type_text", "key_press"}
VALID_KEYS = {"enter", "tab", "space", "backspace"}

CONFIG_FILE = "config.json"


@dataclass
class ServerConfig:
    host: str
    port: int
    target_window: str
    slots: dict


def load_and_validate_config(path):
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

    return ServerConfig(host=host, port=port, target_window=target_window, slots=slots)


def load_or_exit(path):
    """Wrapper de load_and_validate_config para uso na inicialização: registra
    o erro e encerra o processo (sys.exit(1)) em qualquer falha fatal."""
    try:
        config = load_and_validate_config(path)
        logging.info(f"-> Configurações carregadas e validadas com sucesso de {path}.")
        return config
    except FileNotFoundError:
        logging.error(f"-> FATAL ERROR: Arquivo de configuração '{path}' não encontrado.")
        logging.error("-> Crie o arquivo baseado no modelo padrão (config.template.json).")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logging.error(f"-> FATAL ERROR: Formato JSON inválido no '{path}': {e}")
        sys.exit(1)
    except KeyError as e:
        logging.error(f"-> FATAL ERROR: Chave obrigatória ausente no {path}: {e}")
        sys.exit(1)
    except ValueError as e:
        logging.error(f"-> FATAL ERROR: Erro de validação de valor no {path}: {e}")
        sys.exit(1)
