import json
import os


def default_app_config():
    return {
        "SERVER_HOST_IP": "127.0.0.1",
        "SERVER_PORT": 8000,
        "TARGET_WINDOW_TITLE": "Untitled - Notepad",
        "USE_LOG_FILE": False,
        "LOG_FILE_PATH": "",
        "LOG_EXTRACT": {
            "range": {"start_marker": "", "end_marker": ""},
            "fields": [],
        },
        "SCRIPT_FILE": "",
    }


DEFAULT_STEP_DELAY_MS = 300


def default_script_config():
    return {
        "SLOTS": {},
        # Pausa (ms) aplicada pela automação depois de CADA step (clique,
        # duplo clique, digitação, tecla) -- ajustável por PC/script porque a
        # velocidade de resposta do app-alvo varia por máquina.
        "STEP_DELAY_MS": DEFAULT_STEP_DELAY_MS,
    }


def _load_over_defaults(path, defaults):
    """Lê `path` (se existir) por cima de `defaults` e retorna o dict
    resultante. Levanta a exceção original (json/IO) se o arquivo existir mas
    for inválido -- quem chama decide como reportar."""
    data = dict(defaults)

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data.update(json.load(f))

    return data


def load_app_config(path):
    """config.json: apenas as configurações do servidor/app (host, porta,
    janela-alvo, log file). Não inclui SLOTS -- isso vive no script file."""
    return _load_over_defaults(path, default_app_config())


def load_script_config(path):
    """Script file (nome escolhido pelo usuário): apenas SLOTS/Actions."""
    return _load_over_defaults(path, default_script_config())


def normalize_log_extract(log_extract):
    """Retorna (range_data, fields_data) a partir do bloco LOG_EXTRACT,
    migrando o formato legado {"start": {...}, "end": {...}} para o atual
    {"range": {...}, "fields": [...]} quando necessário."""
    log_extract = log_extract or {}
    range_data = log_extract.get("range", {}) or {}

    if not range_data and (log_extract.get("start") or log_extract.get("end")):
        old_start = log_extract.get("start", {}) or {}
        old_end = log_extract.get("end", {}) or {}
        range_data = {
            "start_marker": old_start.get("row_marker", ""),
            "end_marker": old_end.get("row_marker", ""),
        }
        fields_data = [old_start, old_end]
    else:
        fields_data = log_extract.get("fields", []) or []

    return range_data, fields_data


def save(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4)
