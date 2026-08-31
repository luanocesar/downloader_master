import logging

from fastapi import BackgroundTasks, FastAPI
from pydantic import BaseModel

from core import automation
from core.config import ServerConfig, load_and_validate_config


class LabelCodeRequest(BaseModel):
    mapped_labels: dict[str, str]


class TriggerServer:
    """Mantém o estado do servidor entre requisições: a última configuração
    válida carregada e se o robô está ocupado digitando um lote."""

    def __init__(self, config: ServerConfig, config_path: str):
        self.config = config
        self.config_path = config_path
        self.robot_busy = False

    def _run_typing_routine(self, labels_para_digitar):
        try:
            automation.type_labels_into_window(self.config.target_window, self.config.slots, labels_para_digitar)
        finally:
            self.robot_busy = False

    def handle_trigger(self, request: LabelCodeRequest, background_tasks: BackgroundTasks):
        logging.info("\n" + "=" * 50)
        logging.info(">>> NOVO GATILHO RECEBIDO <<<")

        if self.robot_busy:
            logging.warning("-> ALERTA: Robô já está trabalhando! Ignorando pulso duplicado do CLP.")
            return {"status": "busy", "message": "Robô ocupado, ignorando duplicata."}

        # Recarrega o config.json a cada gatilho, para que Slots/Actions
        # adicionados ou editados na UI depois que o servidor já estava rodando
        # sejam respeitados sem precisar reiniciar o processo. HOST/PORT não são
        # recarregados aqui pois o servidor já está vinculado a eles.
        try:
            reloaded = load_and_validate_config(self.config_path)
            self.config.slots = reloaded.slots
            self.config.target_window = reloaded.target_window
        except Exception as e:
            logging.warning(f"-> Falha ao recarregar {self.config_path} ({e}). Usando a última configuração válida em memória.")

        # Tolerante a posições em falta/fora de ordem: cada posição do POST só é
        # usada se existir em SLOTS, sempre amarrada pelo número (chave), nunca
        # pela ordem/posição no payload.
        labels_para_digitar = []
        unknown_keys = []
        for raw_key, label_code in request.mapped_labels.items():
            slot_key = raw_key.strip()

            if not label_code:
                continue
            if slot_key not in self.config.slots:
                unknown_keys.append(raw_key)
                continue
            if not self.config.slots[slot_key].get("enabled", True):
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

        self.robot_busy = True

        logging.info(f"-> Pacote aceito para Slots {[k for k, _ in labels_para_digitar]}. Liberando o Master e iniciando digitação em background...")
        background_tasks.add_task(self._run_typing_routine, labels_para_digitar)

        return {"status": "success", "message": "Iniciando digitação física na tela."}


def create_app(config: ServerConfig, config_path: str) -> FastAPI:
    app = FastAPI()
    trigger_server = TriggerServer(config, config_path)

    @app.post("/trigger")
    def trigger(request: LabelCodeRequest, background_tasks: BackgroundTasks):
        return trigger_server.handle_trigger(request, background_tasks)

    return app
