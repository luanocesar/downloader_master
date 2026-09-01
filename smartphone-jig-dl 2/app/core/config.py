import json
from dataclasses import dataclass

VALID_ACTION_TYPES = {"none", "click", "type_text", "key_press"}
VALID_KEYS = {"enter", "tab", "space", "backspace"}


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
